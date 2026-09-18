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
import collections
import io
import math
import os
import queue
import struct
import threading
import time
from typing import Protocol

from core.logging_setup import get_logger

#: **There was none, and two lines called it.** `log.exception("Поток
#: синтеза оборвался")` and the warning beside it have been in this
#: file since `4.0b-E10` with no `log` anywhere in it — so the one
#: thing that would have explained a broken synthesis stream raised
#: `NameError` inside the handler meant to report the break, on a
#: background thread, where it went to the thread hook as an unrelated
#: crash. Found by counting which modules write to the journal at all.
log = get_logger("speech")

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

    **And neither is the run-up before it.** A word does not begin at full
    voice: "Рина" opens on a consonant quieter than the threshold, and that
    whole chunk — a tenth of a second — used to be thrown away before the
    phrase started. Recognition was then handed a phrase beginning in the
    middle of its first word, and turned «рина что ты умеешь» into
    «приятно что ты умеешь». The first word is the one that matters most:
    in "always listening" it is the name, and a name half-eaten is a name
    not heard. So the last fraction of a second of quiet is kept and goes
    in front of the phrase.
    """

    def __init__(self, rate: int = RATE, threshold: float = 0.02,
                 silence: float = 0.7, min_speech: float = 0.25,
                 max_speech: float = 20.0, lead: float = 0.4):
        self.rate = rate
        self.threshold = threshold
        self.silence = silence
        self.min_speech = min_speech
        self.max_speech = max_speech
        #: How much of the quiet before a phrase goes into it. Long enough
        #: for the attack of a word, short enough not to drag in the end of
        #: the previous one.
        self.lead = lead
        self._buffer = bytearray()
        self._quiet = 0.0
        self._speech = 0.0
        self._speaking = False
        #: The quiet just gone by, waiting to be needed.
        self._lead: "collections.deque[bytes]" = collections.deque()
        self._lead_seconds = 0.0
        #: What the last `feed` put into the phrase — the run-up included.
        #:
        #: For an engine that listens as it goes (`Recogniser.streams`):
        #: it has to be given exactly what the phrase consists of, and in
        #: time. Reading the buffer from outside would hand it the whole
        #: phrase again on every chunk; feeding it the raw chunk would
        #: lose the run-up, which is the beginning of the first word —
        #: the thing this class was just taught to keep.
        self.taken = b""
        #: A phrase ended and was too short to count as one. Whoever is
        #: listening as it goes has already been fed it and has to be
        #: told to forget it.
        self.gave_up = False

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
        self.taken = b""
        self.gave_up = False
        if not pcm:
            return []
        seconds = len(pcm) / (self.rate * SAMPLE_BYTES)
        loud = self.level(pcm) >= self.threshold
        done: list[bytes] = []
        took = bytearray()

        if loud:
            if not self._speaking:
                for earlier in self._lead:
                    self._buffer.extend(earlier)
                    took.extend(earlier)
                self._lead.clear()
                self._lead_seconds = 0.0
            self._speaking = True
            self._quiet = 0.0
            self._speech += seconds
            self._buffer.extend(pcm)
            took.extend(pcm)
        elif self._speaking:
            # Silence inside a phrase is recorded all the same: cutting it
            # out means gluing the words together and getting "setatimer".
            self._buffer.extend(pcm)
            took.extend(pcm)
            self._quiet += seconds
            if self._quiet >= self.silence:
                phrase = self.flush()
                if phrase is not None:
                    done.append(phrase)
                else:
                    self.gave_up = True
        else:
            # Quiet, and nothing being said: remember it in case a word
            # starts in the next chunk. Only the last `lead` seconds —
            # this is a run-up, not a recording of the room.
            self._lead.append(pcm)
            self._lead_seconds += seconds
            while self._lead and self._lead_seconds > self.lead:
                gone = self._lead.popleft()
                self._lead_seconds -= len(gone) / (self.rate * SAMPLE_BYTES)

        if self._speaking and self._speech >= self.max_speech:
            # Too long a phrase is no reason to accumulate endlessly: the
            # person may have left the microphone by a working television.
            phrase = self.flush()
            if phrase is not None:
                done.append(phrase)
            else:
                self.gave_up = True

        self.taken = bytes(took)
        return done

    def flush(self) -> bytes | None:
        """End the phrase by force. `None` means there is nothing to listen to."""
        phrase = bytes(self._buffer)
        speech = self._speech
        self._buffer.clear()
        self._quiet = self._speech = 0.0
        self._speaking = False
        self._lead.clear()
        self._lead_seconds = 0.0
        if speech < self.min_speech:
            return None
        return phrase


# ---------------------------------------------------------------------------
# Recognition (4.0-E03)
# ---------------------------------------------------------------------------
class Recogniser(Protocol):
    """PCM bytes in, text out."""

    name: str

    #: Whether this engine can listen **as the phrase is being said**
    #: rather than only to a finished one. Declared rather than guessed
    #: at by `hasattr`: an engine that grows a method by accident would
    #: silently change which path it is on.
    #:
    #: The whole point is the tail. A phrase handed over whole costs its
    #: recognition time **after** the person has stopped speaking — 620 ms
    #: for Vosk on a phrase of two and a half seconds, measured. Fed as it
    #: goes, the same engine gives the same text 4 ms after the last
    #: chunk, because everything but the last chunk is already done.
    streams: bool

    def available(self) -> bool: ...

    def recognise(self, pcm: bytes, language: str = "ru") -> Heard: ...

    # -- only when `streams` is true ---------------------------------------
    def feed(self, pcm: bytes) -> None:
        """A piece of the phrase now being said."""

    def finish(self) -> Heard:
        """The phrase is over: the text of everything fed since the last one."""

    def reset(self) -> None:
        """Forget what was fed: the phrase came to nothing."""


class DisabledRecogniser:
    """
    There is no recognition, and that is said outright.

    A silent "I heard nothing" would be the worst answer here: the person
    would decide they cannot be heard and start speaking louder.
    """

    name = "disabled"
    streams = False

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

    #: Vosk was built for a stream — that is what `AcceptWaveform` is —
    #: and the old code threw the ability away by handing it whole
    #: phrases after the fact.
    streams = True

    def __init__(self, model_path: str):
        self.model_path = model_path
        self._model = None
        self._error = ""
        #: The live recogniser for the phrase being said, and what it has
        #: already settled on. See `feed`.
        self._live = None
        self._said: list[str] = []

    def available(self) -> bool:
        """
        Is this engine usable — asked without loading anything.

        **Availability is not readiness, and asking must be cheap.** This
        list is drawn every time a person opens the settings, and the first
        edition loaded the model to answer: opening a page would have sat
        for seconds on Vosk and started a download on Whisper. Nobody would
        have connected the two.

        So the question here is "is the engine installed and pointed at
        something", and the model is opened on the first phrase, where
        waiting is expected and a failure has somewhere to be reported.
        """
        if self._model is not None:
            return True
        if not self.model_path:
            self._error = "модель Vosk не выбрана"
            return False
        if not os.path.isdir(self.model_path):
            self._error = "папки с моделью Vosk нет"
            return False
        if not looks_like_vosk_model(self.model_path):
            # Met in real use. A person went to the Vosk download page and
            # brought back `vosk-recasepunc-ru-0.22` — which is on that page
            # and is not a recognition model but a restorer of case and
            # punctuation. The folder existed, the package was there, the
            # settings looked right, and every phrase ended in `Failed to
            # create a model` — the library's words, in English, once per
            # phrase, in the journal only. Four days of "she cannot hear
            # me".
            #
            # Said here rather than at the first phrase because here is
            # where a person is choosing: the settings show the reason an
            # engine cannot be picked.
            self._error = ("это не модель распознавания Vosk: "
                           "в папке нет ни am, ни conf, ни graph")
            return False
        if not installed("vosk"):
            self._error = "пакет vosk не установлен"
            return False
        return True

    def _load(self) -> bool:
        """Open the model. Seconds, so not before the first phrase."""
        if self._model is not None:
            return True
        # **Said out loud, both ways.** Recognition wrote nothing at all
        # about itself — not which engine, not which model, not why it
        # refused — and it is the subsystem whose journal gets read the
        # most: twice a person has gone into it to find out why she does
        # not hear them, and twice the answer had to be guessed from the
        # lines of neighbouring modules. Loading takes seconds and
        # happens once; a line for it is not noise.
        started = time.monotonic()
        try:
            import vosk

            vosk.SetLogLevel(-1)
            self._model = vosk.Model(self.model_path)
            log.info("Vosk: модель загружена за %.1f с — %s",
                     time.monotonic() - started, self.model_path)
            return True
        except Exception as exc:                        # noqa: BLE001
            self._error = str(exc)
            log.warning("Vosk: модель не загрузилась (%s): %s",
                        self.model_path, exc)
            return False

    def recognise(self, pcm: bytes, language: str = "ru") -> Heard:
        if not self.available() or not self._load():
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

    # -- listening as it goes (4.0b-E07) -----------------------------------
    def feed(self, pcm: bytes) -> None:
        """
        Take a piece of the phrase now being said.

        Called from the recognition thread and from nowhere else: the
        worst single piece took 227 ms to think about, and on the thread
        that reads the data channel that is a piece of sound dropped.
        """
        if not self.available() or not self._load():
            return
        import json

        import vosk

        if self._live is None:
            self._live = vosk.KaldiRecognizer(self._model, RATE)
            self._said = []
        # Vosk does its own endpointing and may decide an utterance ended
        # inside our phrase. Then `FinalResult` returns only what came
        # after that point, and the beginning would be lost — so what it
        # settles on is collected as it settles.
        if self._live.AcceptWaveform(pcm):
            self._said.append(json.loads(self._live.Result()).get("text", ""))

    def finish(self) -> Heard:
        """The phrase is over — the text of everything fed since the last one."""
        if self._live is None:
            return Heard(text="")
        import json

        try:
            self._said.append(json.loads(self._live.FinalResult()).get("text", ""))
            return Heard(text=" ".join(p for p in self._said if p).strip())
        except Exception as exc:                        # noqa: BLE001
            return Heard(ok=False, error=str(exc))
        finally:
            self.reset()

    def reset(self) -> None:
        """Forget the phrase: it came to nothing, or somebody changed engine."""
        self._live = None
        self._said = []


def looks_like_vosk_model(folder: str) -> bool:
    """
    Is this a folder a Vosk **recognition** model lives in.

    Judged by what Kaldi needs rather than by the name: models are renamed
    on the way to a person's disk, and a name is not a promise. Any one of
    the three is enough — small and large models, and the ones with a
    dynamic graph, differ in what else they carry, and a check that
    demanded all of them would reject working models.

    Asked because the download page offers more than recognition models,
    and the one that is not one fails with a sentence from the library
    rather than with anything a person can act on.
    """
    return any(os.path.isdir(os.path.join(folder, part))
               for part in ("am", "conf", "graph"))


class WhisperRecogniser:
    """
    Whisper over the bytes that were sent, without a microphone.

    Whisper wants a whole phrase rather than a stream, and a whole phrase is
    exactly what the segmenter hands over — so the fit is better here than
    it was in 3.1.0, where the engine opened the device itself and decided
    when a phrase had ended by its own clock.

    The model is held open between phrases: loading it takes seconds and the
    person is waiting.
    """

    name = "whisper"
    streams = False

    def __init__(self, size: str = "base"):
        self.size = size or "base"
        self._model = None
        self._error = ""

    def available(self) -> bool:
        if self._model is not None:
            return True
        if not installed("whisper"):
            self._error = "пакет openai-whisper не установлен"
            return False
        return True

    def _load(self) -> bool:
        """Load the model — and download it if this is the first time."""
        if self._model is not None:
            return True
        # The first load may also be a download of several hundred
        # megabytes, and from outside that is indistinguishable from
        # "she has stopped answering". A line before and a line after.
        started = time.monotonic()
        log.info("Whisper: загружаю модель «%s»", self.size)
        try:
            import whisper

            self._model = whisper.load_model(self.size)
            log.info("Whisper: модель «%s» готова за %.1f с",
                     self.size, time.monotonic() - started)
            return True
        except Exception as exc:                        # noqa: BLE001
            self._error = str(exc)
            log.warning("Whisper: модель «%s» не загрузилась: %s",
                        self.size, exc)
            return False

    def recognise(self, pcm: bytes, language: str = "ru") -> Heard:
        if not self.available() or not self._load():
            return Heard(ok=False, error=self._error or "stt.unavailable")
        try:
            import array

            import numpy

            samples = array.array("h")
            samples.frombytes(pcm[:len(pcm) - len(pcm) % SAMPLE_BYTES])
            # Whisper takes floats from minus one to one at 16 kHz, and the
            # segmenter hands over exactly 16 kHz — the rate is fixed at the
            # top of this module and declared to the shell when the stream
            # is opened, so there is nothing to resample.
            wave = numpy.frombuffer(samples.tobytes(),
                                    dtype=numpy.int16).astype(
                                        numpy.float32) / 32768.0
            said = self._model.transcribe(
                wave, language=language or None, fp16=False)
            return Heard(text=str(said.get("text", "")).strip())
        except Exception as exc:                        # noqa: BLE001
            return Heard(ok=False, error=str(exc))


def installed(package: str) -> bool:
    """
    Is a package there — asked without running it.

    `import` would answer the same question and cost what the package costs
    to start: `import whisper` pulls in torch, and two and a half seconds
    went on drawing a list of engine names. `find_spec` looks the module up
    and stops there.
    """
    import importlib.util

    try:
        return importlib.util.find_spec(package) is not None
    except (ImportError, ValueError):
        return False


def wave_from(pcm: bytes):
    """PCM bytes -> the floats every Whisper wants, at this module's rate."""
    import array

    import numpy

    samples = array.array("h")
    samples.frombytes(pcm[:len(pcm) - len(pcm) % SAMPLE_BYTES])
    return numpy.frombuffer(samples.tobytes(),
                            dtype=numpy.int16).astype(numpy.float32) / 32768.0


class FasterWhisperRecogniser:
    """
    The same Whisper models, without torch.

    **This is the one that ships.** `openai-whisper` weighs a megabyte and
    pulls in torch, whose wheel is over five hundred and bundles CUDA; an
    installer built around it would be gigabytes for one engine. This runs
    the same models on CTranslate2 — forty megabytes, no torch, and faster
    on a processor besides.

    It carries the same name as the other one on purpose. Which library
    turns the sound into words is our business; a person picks "Whisper",
    and `whisper_for` gives them whichever of the two is installed,
    preferring this.
    """

    name = "whisper"

    #: Whisper looks at a whole piece at once — it has no notion of "so
    #: far". The batch path stays for it, and that is a property of the
    #: model, not a thing left undone.
    streams = False

    def __init__(self, size: str = "base"):
        self.size = size or "base"
        self._model = None
        self._error = ""

    def available(self) -> bool:
        if self._model is not None:
            return True
        if not installed("faster_whisper"):
            self._error = "пакет faster-whisper не установлен"
            return False
        return True

    def _load(self) -> bool:
        if self._model is not None:
            return True
        try:
            from faster_whisper import WhisperModel

            # `int8` on the processor: the models are quantised on load and
            # take about a quarter of the memory at a difference in wording
            # a person does not meet. There is no video card in the promise
            # this program makes.
            self._model = WhisperModel(self.size, device="cpu",
                                       compute_type="int8")
            return True
        except Exception as exc:                        # noqa: BLE001
            self._error = str(exc)
            return False

    def recognise(self, pcm: bytes, language: str = "ru") -> Heard:
        if not self.available() or not self._load():
            return Heard(ok=False, error=self._error or "stt.unavailable")
        try:
            pieces, _ = self._model.transcribe(
                wave_from(pcm), language=language or None,
                # **Whisper answers something to anything.** A second of a
                # quiet room came back as "Редактор субтитров
                # Н.Семкирова" — a line of subtitle credits out of what it
                # was trained on — and the assistant went and searched the
                # internet for it. Measured rather than guessed: on
                # silence this model gives that phrase with a
                # `no_speech_prob` of 0.7, and with the filter it gives
                # nothing at all, twice as fast.
                #
                # The segmenter's threshold does not catch this: a phrase
                # begins on a loud chunk and carries the quiet ones after
                # it, so most of what reaches the model is silence even
                # when a word did sound.
                vad_filter=True,
                # Each phrase on its own. The segmenter hands over whole
                # phrases, and letting the model carry the last one into
                # the next is how "Рина" turns into "Рина, что ты? Рина,
                # что ты?" — the repetition Whisper is known for, and it
                # was in the journal.
                condition_on_previous_text=False)
            kept = [piece for piece in pieces
                    if getattr(piece, "no_speech_prob", 0.0) <= self.NOT_SPEECH]
            return Heard(text="".join(p.text for p in kept).strip())
        except Exception as exc:                        # noqa: BLE001
            return Heard(ok=False, error=str(exc))

    #: Above this the model itself says the sound was probably not speech.
    #:
    #: A second gate behind the filter, and it costs nothing: the number
    #: comes back with every piece. Set where the measured hallucination
    #: sat (0.71) rather than at some round figure — it is the only
    #: reading we have of what one looks like from inside the model.
    NOT_SPEECH = 0.6

    def warm(self) -> bool:
        """
        Load the model before it is needed. Returns whether it is ready.

        The first phrase of a session used to wait for the model: in a
        person's journal a phrase of 1.2 seconds took **eighteen** to come
        back, and eighteen seconds of nothing is indistinguishable from not
        being heard. Loading starts when the microphone opens, where a
        person is already expecting a moment's pause.
        """
        return self.available() and self._load()


def whisper_for(settings) -> Recogniser:
    """
    Whichever Whisper is installed, the light one first.

    One name, two libraries. A person choosing recognition is choosing
    Whisper, not a backend, and offering both under separate names would ask
    them a question whose answer they have no way of having.
    """
    size = str(settings.get("whisper_model", "base") or "base")
    fast = FasterWhisperRecogniser(size)
    return fast if fast.available() else WhisperRecogniser(size)


#: What each engine is called to a person.
#:
#: Written here rather than fetched from the 3.1.0 engine list. That list is
#: assembled by building every engine and asking each whether it can work,
#: which probes the sound devices — two and a half seconds, spent on the one
#: thing we wanted from it, which was the words.
STT_TITLES = {
    "vosk": "Vosk (офлайн, микрофон)",
    "whisper": "Whisper (офлайн, точный)",
    "disabled": "Выключено (нет распознавания)",
}

#: Recognisers the streaming path can actually build (`4.0-E05`).
#:
#: A person picked `whisper` in the settings and heard "recognition is
#: unavailable" for it: the list of choices came from the 3.1.0 engines,
#: which open their own microphone, while this path knew one name and
#: quietly answered `DisabledRecogniser` to every other. Two lists, one of
#: them offering what the other cannot do.
#:
#: Now the offer is made from here, and `tools/test_hearing.py` holds the
#: two together — a name that can be chosen and cannot be built is a defect
#: the person meets as silence.
RECOGNISERS = {
    "vosk": lambda settings: VoskRecogniser(
        str(settings.get("vosk_model", "") or "")),
    "whisper": whisper_for,
    "disabled": lambda settings: DisabledRecogniser(),
}


def recogniser_for(settings) -> Recogniser:
    """Which recognition is chosen in the settings."""
    engine = str(settings.get("stt_engine", "disabled") or "disabled")
    build = RECOGNISERS.get(engine)
    return build(settings) if build else DisabledRecogniser()


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
    streams = False

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
    #: Piper makes a whole utterance at once, locally and quickly. There
    #: is nothing to stream: by the time the first piece could be handed
    #: over, the last one exists too.
    streams = False

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


class _Arriving(io.RawIOBase):
    """
    A file that is still being written, read by whoever decodes it.

    The decoder wants a file and the network gives pieces; this is the
    join. `read` waits for the next piece rather than returning empty —
    an empty read means the end of the file, and ending a file because
    the network paused for a moment would cut the reply.
    """

    def __init__(self):
        self._parts: "queue.Queue" = queue.Queue()
        self._rest = b""
        self._over = False

    def put(self, piece: "bytes | None") -> None:
        self._parts.put(piece)

    def readable(self) -> bool:
        return True

    def read(self, size: int = -1) -> bytes:
        """
        Whatever is here, and only wait if nothing is.

        **A short read is allowed and a long wait is not.** The decoder
        asks in thirty-two kilobyte mouthfuls; waiting for a whole one
        means waiting for most of the reply, and measured it was exactly
        that — the first frame came out 365 ms in, at the moment the
        thirty-two kilobytes were complete, not at the moment there was
        something to decode. Returning less than was asked for is what
        `read` is allowed to do, and what makes this a stream.
        """
        want = size if size > 0 else 1
        while not self._rest and not self._over:
            piece = self._parts.get()
            if piece is None:
                self._over = True
                break
            self._rest += piece
        while len(self._rest) < want and not self._over:
            try:
                piece = self._parts.get_nowait()
            except queue.Empty:
                break
            if piece is None:
                self._over = True
                break
            self._rest += piece
        out, self._rest = self._rest[:size], self._rest[size:]
        return out


def pcm_from_stream(pieces, container: str = "mp3"):
    """
    Decode arriving audio into PCM as it arrives. Yields `(bytes, rate)`.

    **The other half of `4.0b-E10`.** An engine that hands over sound as
    it makes it is of no use if the decoder waits for the last byte:
    `soundfile` wants a whole file, and a whole file is exactly what we
    are trying not to wait for. PyAV reads a stream that cannot be
    rewound, which is what this is — and it is already in the runtime,
    because `faster-whisper` brings it.

    The filling runs in a thread of its own because the decoder pulls:
    it asks the file for bytes and blocks until they come, so somebody
    else has to be putting them there.
    """
    import av

    feed = _Arriving()

    def fill():
        try:
            for piece in pieces:
                if piece:
                    feed.put(piece)
        except Exception:                               # noqa: BLE001
            log.exception("Поток синтеза оборвался")
        finally:
            feed.put(None)

    filler = threading.Thread(target=fill, name="rina-tts-feed", daemon=True)
    filler.start()

    box = None
    try:
        # The smallest probe there is, because there is nothing to
        # probe for: the container is named outright, so reading ahead
        # to guess it is reading a person is waiting through. Measured
        # on a real reply: opening takes 21 ms this way, 65 at four
        # kilobytes, 92 with the defaults.
        box = av.open(feed, format=container,
                      options={"probesize": "32", "analyzeduration": "0"})
        # No rate given: the engine's own rate is kept and declared when
        # the stream to the shell is opened. Resampling without being
        # asked costs time and quality for nothing.
        resampler = av.AudioResampler(format="s16", layout="mono")
        for frame in box.decode(box.streams.audio[0]):
            for made in resampler.resample(frame):
                yield made.to_ndarray().tobytes(), int(made.sample_rate)
    except Exception as trouble:                        # noqa: BLE001
        log.warning("Не удалось разобрать поток синтеза: %s", trouble)
    finally:
        if box is not None:
            try:
                box.close()
            except Exception:                           # noqa: BLE001
                pass


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

    @property
    def streams(self) -> bool:
        """Whether this engine gives out sound as it makes it (`4.0b-E10`)."""
        try:
            return bool(getattr(self._engine(), "streams", False))
        except Exception:                               # noqa: BLE001
            return False

    def stream(self, text: str, voice: str = "", rate: int = 100):
        """The same speech as `synthesize`, in pieces, as it is made."""
        engine = self._engine()
        volume = 75
        if self._settings is not None:
            try:
                volume = int(self._settings.get("volume", 75) or 75)
            except (TypeError, ValueError):
                volume = 75
        pieces = engine.stream(text, voice=voice or None, volume=volume,
                               rate=rate)
        for pcm, hertz in pcm_from_stream(pieces,
                                          getattr(engine, "stream_format",
                                                  "mp3")):
            self._rate = hertz
            yield pcm

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
#: Words that end in a dot and do not end a sentence. Short on purpose:
#: a long list of abbreviations is a list nobody keeps up, and the cost of
#: a miss here is one seam in the middle of a phrase, not a lost word.
_NOT_THE_END = ("т", "д", "е", "п", "г", "гг", "мин", "сек", "ч", "стр",
                "им", "тыс", "млн", "руб", "см", "км", "кг", "напр")

#: Below this many characters a piece is not said on its own but joined
#: to the next. "Да." synthesised alone plays out in a quarter of a
#: second and leaves the queue empty while the next sentence is still
#: being made — and an empty queue between two halves of one answer is a
#: gap a person hears as a stutter.
#:
#: Twenty, because a character is roughly seventy milliseconds of speech:
#: twenty of them is about a second and a half of sound, comfortably
#: longer than one request to a synthesiser. Higher and ordinary short
#: sentences stop being said on their own — the first cut of this was
#: forty, and "Я могу запускать много разных программ." at thirty-eight
#: swallowed the sentence after it, which is the whole gain given back.
LEAST_PIECE = 20


def sentences(text: str, least: int = LEAST_PIECE) -> list[str]:
    """
    Cut a reply into pieces that can be spoken one after another.

    **Why at all** (`4.0b-E09`): synthesis of a whole reply is waited out
    whole. Cut into sentences, the first one can be heard while the rest
    is still being made, and the wait before the first syllable stops
    depending on how long the answer is.

    Where **not** to cut matters more than where to: a dot inside a
    number, a dot after an abbreviation, a dot before a lower-case letter
    — three ways to get a seam in the middle of a sentence, which sounds
    worse than a long wait.
    """
    text = (text or "").strip()
    if not text:
        return []

    pieces: list[str] = []
    piece = ""
    for i, sign in enumerate(text):
        piece += sign
        if sign not in ".!?…":
            continue
        rest = text[i + 1:]
        if rest and not rest[0].isspace():
            continue                        # "3.14", "то-то.И" — not an end
        if sign == "." and i and text[i - 1].isdigit():
            continue                        # "в 10. 5 МБ" is not two sentences
        # The last word, and inside it the part after the last dot:
        # "и т.д." is one token, and the piece of it that says this is
        # an abbreviation is the "д".
        word = piece.rstrip(".!?… ").split()[-1:]
        tail = word[0].rstrip(".").split(".")[-1].lower() if word else ""
        if sign == "." and tail in _NOT_THE_END:
            continue
        ahead = rest.lstrip()
        if ahead and ahead[0].islower():
            continue                        # a sentence does not begin small
        pieces.append(piece.strip())
        piece = ""
    if piece.strip():
        pieces.append(piece.strip())

    # Too short a piece joins the one after it — see `LEAST_PIECE`. The
    # last one has nothing to join, so it joins the one before instead.
    joined: list[str] = []
    for part in pieces:
        if joined and len(joined[-1]) < least:
            joined[-1] = joined[-1] + " " + part
        else:
            joined.append(part)
    if len(joined) > 1 and len(joined[-1]) < least:
        tail = joined.pop()
        joined[-1] = joined[-1] + " " + tail
    return joined


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
