# -*- coding: utf-8 -*-
"""
Speech in the core: recognise what was sent, synthesise what is answered.

Plan items `4.0-E03` (recognition) and `4.0-E04` (synthesis).

**What changes here compared with 3.1.0.** There the recognition engines
recorded from the microphone themselves (`listen_once`), and the synthesis
engines played the sound themselves (`speak`). In the split program both
belong to the shell: it has the devices and the low latency. What is left to
the core is what makes it the core — the models.

Hence two new boundaries, and both are narrow:

    Recogniser    PCM bytes  ->  text
    Synthesiser   text       ->  PCM bytes

Neither of them knows anything about devices or about channels. That makes
it possible to check them with synthetic sound, and it also means a
recording from a file can be recognised — while looking into a complaint,
for instance.

**The microphone arrives at 16 kHz, mono, 16 bit** — the format both Vosk
and Whisper understand, and the one the shell captures in (`4.0-F09`).

**Synthesis declares its own rate rather than being adjusted.** The models
speak at different ones: that is exactly what the `format` field in
`stream.open` (§8) is for. Resampling without a filter gives artefacts, and
with a filter it is work done in order to avoid filling in one field.

**Slicing into phrases lives here, not in the shell.** The shell counts the
level for the instrument strip, but the decision "speech has ended" is taken
next to recognition: only here is it known how much silence counts as a
pause inside a sentence and how much as the end of a phrase, and that
depends on the model.
"""

import array
import math
import struct
from typing import Protocol

#: The format sound travels in between the shell and the core.
RATE = 16000
CHANNELS = 1
BITS = 16
SAMPLE_BYTES = 2


class Heard:
    """What was heard. Empty text with `ok` means "silence, but all is well"."""

    __slots__ = ("text", "ok", "error")

    def __init__(self, text="", ok=True, error=""):
        self.text = text
        self.ok = ok
        self.error = error

    def __repr__(self):
        return f"Heard({self.text!r}, ok={self.ok}, error={self.error!r})"


class Segmenter:
    """
    Cuts a continuous stream into phrases by silence.

    A plain energy threshold with a release delay — not because it is better
    than a neural one but because it is more honest: a real VAD will appear
    in 5.0 along with streaming, and until then there is no point pretending
    there is one.

    **The release delay is obligatory.** Without it a phrase tears at every
    pause between words: "set… a timer" turns into two phrases, and the
    second arrives without the first. Half a second of silence is a pause, a
    second and a half is the end of a phrase.

    **The beginning of a phrase is not lost.** The chunk on which the sound
    first crossed the threshold already contains the beginning of a word, so
    it goes into the phrase whole rather than from the point where the
    threshold fired.
    """

    def __init__(self, rate: int = RATE, threshold: float = 0.02,
                 silence: float = 0.7, min_speech: float = 0.25,
                 max_speech: float = 20.0):
        self.rate = rate
        self.threshold = threshold
        self.silence = silence
        self.min_speech = min_speech
        self.max_speech = max_speech
        self._buffer = bytearray()
        self._quiet = 0.0
        self._speech = 0.0
        self._speaking = False

    @staticmethod
    def level(pcm: bytes) -> float:
        """
        Root-mean-square loudness, 0..1.

        Computed by hand rather than with `audioop.rms`: the module is
        declared obsolete and **removed in Python 3.13**. The core will
        outlive that version, and discovering such a thing while upgrading
        the interpreter is the worst possible moment. There is nothing to
        compute here: fifteen hundred samples per chunk.
        """
        if len(pcm) < SAMPLE_BYTES:
            return 0.0
        samples = array.array("h")
        samples.frombytes(pcm[:len(pcm) - len(pcm) % SAMPLE_BYTES])
        if not samples:
            return 0.0
        total = sum(value * value for value in samples)
        return math.sqrt(total / len(samples)) / 32768.0

    def feed(self, pcm: bytes) -> list[bytes]:
        """Take a chunk and return the phrases that have finished."""
        if not pcm:
            return []
        seconds = len(pcm) / (self.rate * SAMPLE_BYTES)
        loud = self.level(pcm) >= self.threshold
        done: list[bytes] = []

        if loud:
            self._speaking = True
            self._quiet = 0.0
            self._speech += seconds
            self._buffer.extend(pcm)
        elif self._speaking:
            # Silence inside a phrase is recorded all the same: cutting it
            # out means gluing the words together and getting "setatimer".
            self._buffer.extend(pcm)
            self._quiet += seconds
            if self._quiet >= self.silence:
                phrase = self.flush()
                if phrase is not None:
                    done.append(phrase)

        if self._speaking and self._speech >= self.max_speech:
            # Too long a phrase is no reason to accumulate endlessly: the
            # person may have left the microphone by a working television.
            phrase = self.flush()
            if phrase is not None:
                done.append(phrase)
        return done

    def flush(self) -> bytes | None:
        """End the phrase by force. `None` means there is nothing to listen to."""
        phrase = bytes(self._buffer)
        speech = self._speech
        self._buffer.clear()
        self._quiet = self._speech = 0.0
        self._speaking = False
        if speech < self.min_speech:
            return None
        return phrase


# ---------------------------------------------------------------------------
# Recognition (4.0-E03)
# ---------------------------------------------------------------------------
class Recogniser(Protocol):
    """PCM bytes in, text out."""

    name: str

    def available(self) -> bool: ...

    def recognise(self, pcm: bytes, language: str = "ru") -> Heard: ...


class DisabledRecogniser:
    """
    There is no recognition, and that is said outright.

    A silent "I heard nothing" would be the worst answer here: the person
    would decide they cannot be heard and start speaking louder.
    """

    name = "disabled"

    def available(self) -> bool:
        return False

    def recognise(self, pcm: bytes, language: str = "ru") -> Heard:
        return Heard(ok=False, error="stt.unavailable")


class VoskRecogniser:
    """
    Vosk over the bytes that were sent, without a microphone.

    Vosk can take a stream in chunks, and that is exactly what is needed:
    the sound comes from the shell over the data channel rather than from a
    device. The model is kept open between phrases — loading it takes
    seconds.
    """

    name = "vosk"

    def __init__(self, model_path: str):
        self.model_path = model_path
        self._model = None
        self._error = ""

    def available(self) -> bool:
        if self._model is not None:
            return True
        if not self.model_path:
            self._error = "модель Vosk не выбрана"
            return False
        try:
            import vosk

            vosk.SetLogLevel(-1)
            self._model = vosk.Model(self.model_path)
            return True
        except Exception as exc:                        # noqa: BLE001
            self._error = str(exc)
            return False

    def recognise(self, pcm: bytes, language: str = "ru") -> Heard:
        if not self.available():
            return Heard(ok=False, error=self._error or "stt.unavailable")
        try:
            import json

            import vosk

            recogniser = vosk.KaldiRecognizer(self._model, RATE)
            recogniser.AcceptWaveform(pcm)
            said = json.loads(recogniser.FinalResult()).get("text", "")
            return Heard(text=said.strip())
        except Exception as exc:                        # noqa: BLE001
            return Heard(ok=False, error=str(exc))


def recogniser_for(settings) -> Recogniser:
    """Which recognition is chosen in the settings."""
    engine = str(settings.get("stt_engine", "disabled") or "disabled")
    if engine == "vosk":
        return VoskRecogniser(str(settings.get("vosk_model", "") or ""))
    return DisabledRecogniser()


# ---------------------------------------------------------------------------
# Synthesis (4.0-E04)
# ---------------------------------------------------------------------------
class Synthesiser(Protocol):
    """
    Text in, PCM bytes out.

    `sample_rate` is declared rather than assumed: different models speak at
    different rates, and the `format` field in `stream.open` exists
    precisely to say so rather than to be guessed at.
    """

    name: str
    sample_rate: int

    def available(self) -> bool: ...

    def synthesize(self, text: str, voice: str = "", rate: int = 100) -> bytes: ...


class SilentSynthesiser:
    """There is no synthesis: the answer stays text. A lawful mode, not a breakage."""

    name = "silent"
    sample_rate = RATE

    def available(self) -> bool:
        return False

    def synthesize(self, text: str, voice: str = "", rate: int = 100) -> bytes:
        return b""


class PiperSynthesiser:
    """
    Piper: Rina's own voice, locally.

    It gives out raw samples rather than a file: a file would have to be
    written to disk, read and deleted — three operations for the sake of
    what is already in memory.
    """

    name = "piper"

    def __init__(self, model_path: str):
        self.model_path = model_path
        self._voice = None
        self._error = ""

    def available(self) -> bool:
        if self._voice is not None:
            return True
        if not self.model_path:
            self._error = "модель Piper не выбрана"
            return False
        try:
            from piper import PiperVoice

            self._voice = PiperVoice.load(self.model_path)
            return True
        except Exception as exc:                        # noqa: BLE001
            self._error = str(exc)
            return False

    @property
    def sample_rate(self) -> int:
        """
        The rate the model speaks at.

        Not resampled to the microphone's rate: the data stream has a
        `format` field (§8), and declaring one's own rate is cheaper and
        more honest than resampling. Resampling without a filter gives
        artefacts, and with a filter it is work done in order to avoid
        filling in one field.
        """
        if self._voice is None:
            return RATE
        return int(getattr(self._voice.config, "sample_rate", RATE))

    def synthesize(self, text: str, voice: str = "", rate: int = 100) -> bytes:
        if not self.available():
            return b""
        chunks = bytearray()
        for piece in self._voice.synthesize_stream_raw(text):
            chunks.extend(piece)
        return bytes(chunks)


def pcm_from_file(path: str) -> tuple[bytes, int]:
    """
    Read a sound file as 16-bit mono PCM. Returns the bytes and the rate.

    The 3.1.0 engines give out a file — mp3 for the network ones, wav for
    the system one — while the wire carries raw samples (§8). There is
    deliberately no resampling here: the rate is declared in `format` when
    the stream is opened, and saying "I speak at 24000" is cheaper and more
    honest than resampling without a filter.
    """
    try:
        import numpy
        import soundfile

        data, rate = soundfile.read(path, dtype="int16", always_2d=True)
        # Mono: the wire and the shell's speaker agreed on one channel.
        # Mixing in int16 will not do — it overflows; we count in a wide type.
        if data.shape[1] > 1:
            data = data.mean(axis=1).astype(numpy.int16)
        else:
            data = data[:, 0]
        return data.tobytes(), int(rate)
    except Exception:                                   # noqa: BLE001
        pass

    # A fallback path without third-party packages — for wav only. The
    # network engines give out mp3, and for them soundfile is obligatory;
    # saying so is more honest than staying silent by voice.
    import wave

    with wave.open(path, "rb") as source:
        if source.getsampwidth() != SAMPLE_BYTES:
            return b"", RATE
        frames = source.readframes(source.getnframes())
        if source.getnchannels() > 1:
            frames = b"".join(frames[i:i + SAMPLE_BYTES]
                              for i in range(0, len(frames),
                                             SAMPLE_BYTES * source.getnchannels()))
        return frames, source.getframerate()


class EngineSynthesiser:
    """
    Synthesis by the 3.1.0 engines: edge, gtts, pyttsx3, piper.

    The engines were written for "say it out loud right here": each made a
    temporary file and played it itself. In 4.0 the shell plays, so a file
    is taken (`TTSEngine.render`) rather than sound from the core's speaker.
    A core without a shell stays silent — and that is right: a process that
    can run as a service must not have a voice of its own.

    There is no class of its own per engine here: the difference between
    them is inside `voice/tts.py`, and to the core they are all one and the
    same — text in, a file out. A second list of engines would part company
    with the first.
    """

    def __init__(self, engine_id: str, settings=None):
        self.name = engine_id
        self._settings = settings
        self._rate = RATE
        self.last_error = ""

    def _engine(self):
        from voice import tts

        return tts.get_engine(self.name)

    def available(self) -> bool:
        try:
            return bool(self._engine().available)
        except Exception as exc:                        # noqa: BLE001
            self.last_error = str(exc)
            return False

    @property
    def sample_rate(self) -> int:
        """The rate of the last synthesis; before the first, the microphone's rate."""
        return self._rate

    def synthesize(self, text: str, voice: str = "", rate: int = 100) -> bytes:
        import os

        if not text.strip():
            return b""
        volume = 75
        if self._settings is not None:
            try:
                volume = int(self._settings.get("volume", 75) or 75)
            except (TypeError, ValueError):
                volume = 75

        path = ""
        try:
            path = self._engine().render(text, voice=voice or None,
                                         volume=volume, rate=rate) or ""
            if not path or not os.path.isfile(path):
                self.last_error = "движок не отдал файл"
                return b""
            pcm, self._rate = pcm_from_file(path)
            return pcm
        except Exception as exc:                        # noqa: BLE001
            self.last_error = str(exc)
            return b""
        finally:
            # The temporary file is ours: the engine created it at our request.
            if path:
                try:
                    os.remove(path)
                except OSError:
                    pass


def synthesiser_for(settings) -> Synthesiser:
    """
    Which synthesis is chosen in the settings.

    This used to recognise Piper alone, and everything else silently became
    silence: a person picked Edge, the core answered in text and did not
    speak. Silence instead of a voice is the worst kind of failure, because
    it looks like a working program.
    """
    engine = str(settings.get("tts_engine", "silent") or "silent")
    if engine in ("", "silent"):
        return SilentSynthesiser()
    if engine == "piper" and settings.get("piper_model"):
        # A road of its own: Piper gives samples straight into memory, without a file.
        return PiperSynthesiser(str(settings.get("piper_model", "") or ""))
    return EngineSynthesiser(engine, settings)


# ---------------------------------------------------------------------------
# Common
# ---------------------------------------------------------------------------
def tone(seconds: float, hertz: float = 440.0, rate: int = RATE) -> bytes:
    """
    Synthetic sound for the checks.

    It lives in the core rather than in a test, because both sides need it:
    the core's test checks the slicing with it, the shell's test the
    playback queue, and two copies of one sine wave would part company in
    loudness.
    """
    samples = int(rate * seconds)
    return b"".join(
        struct.pack("<h", int(math.sin(2 * math.pi * hertz * i / rate) * 12000))
        for i in range(samples))


def silence(seconds: float, rate: int = RATE) -> bytes:
    return b"\x00" * (int(rate * seconds) * SAMPLE_BYTES)
