"""
The text-to-speech layer with a choice of engine.

The TTSEngine abstraction makes it possible to choose "the TTS itself" (not
only the voice):
  - Pyttsx3Engine   — offline, system synthesis (SAPI5/NSSS/espeak)
  - GttsEngine      — online, Google TTS (more natural, needs the internet)
  - SilentEngine    — no speech (toast/text only), always available

Every backend is optional: if the library is not installed, the engine is
marked unavailable (available=False) and is not offered. SilentEngine is
always there, so the application works even without a single TTS library.

Synthesis blocks, so it is called from a background thread (see
voice/service.py) rather than directly from the GUI.

Playback goes through a single queue (_Playback): answers sound one at a
time and in the order they arrive. Every synthesis writes into a temporary
file of its own, which is deleted after playing.
"""

import os
import queue
import subprocess
import sys
import tempfile
import threading

from core.logging_setup import get_logger


log = get_logger("tts")


class TTSEngine:
    id = "base"
    label = "Base"

    @property
    def available(self) -> bool:
        return False

    def voices(self):
        """A list of (voice_id, human_label) of the available voices."""
        return []

    def render(self, text, voice=None, volume=75, rate=100):
        """
        Synthesise into a file and return the path. `None` means it did not
        work.

        Appeared for 4.0: synthesis in the core, playback in the shell
        (`4.0-F10`). An engine had to make a file before this too — each
        wrote a temporary one and played it on the spot; the split merely
        says that step out loud. Whoever called deletes it.
        """
        return None

    #: Whether this engine gives out sound **as it makes it**, rather than
    #: only when it has made all of it (`4.0b-E10`).
    #:
    #: Declared rather than guessed at by `hasattr`, for the same reason
    #: as `Recogniser.streams`: a method that appears by accident would
    #: silently move an engine onto a path nobody checked it on.
    streams = False

    #: What `stream` gives out, as a container name for the decoder.
    #: Edge speaks mp3; an engine that hands over raw samples would say
    #: so here and skip the decoding altogether.
    stream_format = "mp3"

    def stream(self, text, voice=None, volume=75, rate=100):
        """
        Yield the audio of `text` in pieces, encoded as `stream_format`.

        Only where `streams` is true. The pieces are what the engine has
        managed to make so far — for a network engine, what has arrived
        so far — so the first of them exists long before the last.
        """
        raise NotImplementedError

    def speak(self, text, voice=None, volume=75, rate=100):
        """Blockingly says the text out loud. rate/volume are per cent (100 = normal)."""
        path = self.render(text, voice=voice, volume=volume, rate=rate)
        if path:
            _play_audio_file(path, delete_after=True)

    def stop(self):
        pass


# ---------------------------------------------------------------------------
class SilentEngine(TTSEngine):
    """Voices nothing — text/toast only. Always available."""
    id = "silent"
    label = "Без озвучки (только текст)"

    @property
    def available(self):
        return True

    def voices(self):
        return [("none", "— нет голоса —")]

    def render(self, text, voice=None, volume=75, rate=100):
        return None

    def speak(self, text, voice=None, volume=75, rate=100):
        # deliberately quiet; a small pause ~ the time of "saying it"
        return


# ---------------------------------------------------------------------------
class Pyttsx3Engine(TTSEngine):
    """Offline system TTS through pyttsx3."""
    id = "pyttsx3"
    label = "Системный (pyttsx3, офлайн)"

    def __init__(self):
        self._engine = None
        self._voices_cache = None
        self._lock = threading.Lock()

    def _try_import(self):
        try:
            import pyttsx3  # noqa
            return pyttsx3
        except Exception:
            return None

    @property
    def available(self):
        return self._try_import() is not None

    def _get_engine(self):
        mod = self._try_import()
        if mod is None:
            return None
        if self._engine is None:
            self._engine = mod.init()
        return self._engine

    def voices(self):
        if self._voices_cache is not None:
            return self._voices_cache
        eng = self._get_engine()
        result = []
        if eng is not None:
            try:
                for v in eng.getProperty("voices"):
                    name = getattr(v, "name", None) or getattr(v, "id", "voice")
                    result.append((v.id, name))
            except Exception:
                pass
        if not result:
            result = [("default", "Системный голос")]
        self._voices_cache = result
        return result

    def _tune(self, eng, voice, volume, rate):
        if voice and voice != "default":
            eng.setProperty("voice", voice)
        eng.setProperty("volume", max(0.0, min(1.0, volume / 100.0)))
        # pyttsx3 rate ~ words/min; 200 is about normal. We scale from rate%.
        eng.setProperty("rate", int(200 * (rate / 100.0)))

    def render(self, text, voice=None, volume=75, rate=100):
        eng = self._get_engine()
        if eng is None:
            return None
        with self._lock:
            try:
                self._tune(eng, voice, volume, rate)
                tmp = new_temp_file(".wav", "rina_pyttsx3_")
                eng.save_to_file(text, tmp)
                eng.runAndWait()
                return tmp if os.path.isfile(tmp) else None
            except Exception:
                return None

    def speak(self, text, voice=None, volume=75, rate=100):
        # Says it itself rather than through a file: system synthesis can do
        # that, and an extra round through the disk would add latency where
        # there is none.
        eng = self._get_engine()
        if eng is None:
            return
        with self._lock:
            try:
                self._tune(eng, voice, volume, rate)
                eng.say(text)
                eng.runAndWait()
            except Exception:
                pass

    def stop(self):
        if self._engine is not None:
            try:
                self._engine.stop()
            except Exception:
                pass


# ---------------------------------------------------------------------------
class GttsEngine(TTSEngine):
    """Online Google TTS (a natural voice, needs the internet)."""
    id = "gtts"
    label = "Google TTS (онлайн)"

    LANG_VOICES = [
        ("ru", "Русский"), ("en", "English"), ("uk", "Українська"),
        ("es", "Español"), ("de", "Deutsch"),
    ]

    def _try_import(self):
        try:
            from gtts import gTTS  # noqa
            return gTTS
        except Exception:
            return None

    def _can_play(self):
        # playback through sounddevice + soundfile (as with Edge/Piper)
        try:
            import soundfile  # noqa
            import sounddevice  # noqa
            return True
        except Exception:
            return False

    @property
    def available(self):
        return self._try_import() is not None and self._can_play()

    def voices(self):
        return list(self.LANG_VOICES)

    def render(self, text, voice=None, volume=75, rate=100):
        gTTS = self._try_import()
        if gTTS is None:
            return None
        lang = voice if voice in dict(self.LANG_VOICES) else "ru"
        try:
            tmp = new_temp_file(".mp3", "rina_gtts_")
            gTTS(text=text, lang=lang, slow=(rate < 80)).save(tmp)
            return tmp
        except Exception:
            return None


# ---------------------------------------------------------------------------
def _selected_output_device():
    """The index of the chosen output device, or None (the default)."""
    try:
        from core.settings_store import settings
        dev = settings.get("output_device", "default")
        if dev and dev != "default":
            return int(dev)
    except Exception:
        pass
    return None


def new_temp_file(suffix, prefix="rina_tts_"):
    """
    A separate file for every synthesis.

    The names used to be constant ("rina_gtts.mp3"), and two answers in a
    row overwrote each other's file: the first broke off in the middle, and
    the second could read half-written data.
    """
    fd, path = tempfile.mkstemp(prefix=prefix, suffix=suffix)
    os.close(fd)            # the synthesiser will write; it needs the path
    return path


class _Playback:
    """
    The single playback worker.

    Rina's answers must sound one at a time and whole. Without a queue two
    syntheses that began almost at the same time played at the same time:
    both were audible and neither was.
    """

    def __init__(self):
        self._queue = queue.Queue()
        self._worker = None
        self._lock = threading.Lock()

    def _ensure_worker(self):
        with self._lock:
            if self._worker is None or not self._worker.is_alive():
                self._worker = threading.Thread(
                    target=self._run, name="tts-playback", daemon=True)
                self._worker.start()

    def _run(self):
        while True:
            job = self._queue.get()
            path, delete_after, done, result = job
            try:
                result.append(_play_now(path))
            except Exception:
                # one file's failure must not carry off the worker: the
                # next answer is obliged to sound
                log.exception("Ошибка воспроизведения")
                result.append(False)
            finally:
                if delete_after:
                    try:
                        os.remove(path)
                    except OSError:
                        pass
                done.set()

    def play(self, path, delete_after=False, wait=True):
        """Puts a file into the queue. With wait=True it waits for the end."""
        self._ensure_worker()
        done = threading.Event()
        result = []
        self._queue.put((path, delete_after, done, result))
        if not wait:
            return True
        done.wait()
        return bool(result and result[0])

    def pending(self):
        return self._queue.qsize()


_playback = _Playback()


def _play_audio_file(path, delete_after=False):
    """Put a file into the playback queue and wait for it."""
    return _playback.play(path, delete_after=delete_after, wait=True)


def _play_now(path):
    """The playing itself. Called only by the queue's worker."""
    device = _selected_output_device()

    # if a particular output device is chosen, we play through sounddevice,
    # since only it can direct sound to a given device.
    if device is not None:
        try:
            import soundfile as sf
            import sounddevice as sd
            data, sr = sf.read(path, dtype="float32")
            sd.play(data, sr, device=device)
            sd.wait()
            return True
        except Exception:
            pass  # it did not work — we fall through to the general ways below

    # 1) playsound (light, the default system output)
    try:
        import playsound
        playsound.playsound(path, True)
        return True
    except Exception:
        pass
    # 2) sounddevice + soundfile (what is already installed for the microphone)
    try:
        import soundfile as sf
        import sounddevice as sd
        data, sr = sf.read(path, dtype="float32")
        kwargs = {"device": device} if device is not None else {}
        sd.play(data, sr, **kwargs)
        sd.wait()
        return True
    except Exception:
        pass
    # 3) the system player as a last resort
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)  # noqa
            return True
        elif sys.platform == "darwin":
            subprocess.Popen(["afplay", path])
            return True
        else:
            subprocess.Popen(["aplay", path])
            return True
    except Exception:
        return False


class EdgeTTSEngine(TTSEngine):
    """
    Microsoft Edge Neural TTS (edge-tts): free, online, very natural neural
    voices. Requires the edge-tts package. This is an excellent "default"
    option for good speech without keys.
    """
    id = "edge"
    label = "Edge Neural (онлайн, естественный)"

    VOICES = [
        ("ru-RU-SvetlanaNeural", "Светлана (ru, жен.)"),
        ("ru-RU-DmitryNeural", "Дмитрий (ru, муж.)"),
        ("en-US-AriaNeural", "Aria (en, жен.)"),
        ("en-US-GuyNeural", "Guy (en, муж.)"),
        ("uk-UA-PolinaNeural", "Поліна (uk, жен.)"),
        ("de-DE-KatjaNeural", "Katja (de, жен.)"),
    ]

    def _try_import(self):
        try:
            import edge_tts  # noqa
            return edge_tts
        except Exception:
            return None

    @property
    def available(self):
        return self._try_import() is not None

    def voices(self):
        return list(self.VOICES)

    #: Edge makes the sound on somebody else's computer and sends it as
    #: it goes — the one engine here that can (`4.0b-E10`).
    streams = True
    stream_format = "mp3"

    #: The host the service lives on, for the bypass list.
    HOST = "speech.platform.bing.com"

    @classmethod
    def _through(cls):
        """The proxy to reach the service through, or None for direct.

        **Found by measurement, on a machine where Rina took sixteen
        seconds to start speaking.** The route to Microsoft's speech
        service was slow from that machine — 15.7 seconds to the first
        byte — and fast through the proxy the person had set up:
        under a second. Every browser on that machine used the proxy;
        Rina did not, and so she alone was sixteen times slower.

        **The rest of this program already goes that way.** Model
        downloads use `urllib`, which on Windows reads the system
        proxy out of the registry; the web search opens the person's
        browser, which honours it too. Edge was the one place that
        went direct — not by decision, but because nobody had looked.
        `edge-tts` reads `HTTPS_PROXY` from the environment on its own
        (`trust_env=True`), and the environment is exactly where a
        proxy set system-wide is **not**: a window started from the
        desktop carries the variables that existed when the desktop
        started.

        `getproxies()` answers both cases in one call — the variables
        when they are set, the registry when they are not — so there
        is one answer here rather than two rules that disagree.

        The bypass list is honoured: a person who excluded a host
        excluded it, and routing it anyway would be deciding their
        network for them.
        """
        import urllib.request

        try:
            proxy = urllib.request.getproxies().get("https")
            return proxy if proxy and not cls._bypassed() else None
        except Exception:                               # noqa: BLE001
            # A machine whose proxy settings cannot be read is a
            # machine that goes direct, as it did before.
            return None

    @classmethod
    def _bypassed(cls):
        """Is the service in the "go direct" list — by name alone.

        **`urllib.request.proxy_bypass` is not used, and that is the
        whole fix.** On Windows it enriches the host with its address
        and its fully qualified name before comparing, and
        `socket.getfqdn` is a reverse lookup: measured on the machine
        this was found on, **fifteen seconds**. Every one of them was
        spent to decide that a public Microsoft hostname is not in
        somebody's list of local exceptions.

        That is also the whole of the original fault. `aiohttp` calls
        the same function on every request when no proxy is given to
        it and `trust_env` is on — which is exactly the state a window
        started from the desktop is in, because a proxy set
        system-wide is in the registry and not in the environment. So
        Rina paid fifteen seconds before every sentence, and paid it
        again for the next one; with the variables set she took the
        environment branch, a string comparison, and was fast. Two
        machines, one program, a sixteenfold difference, and nothing
        anywhere said why.

        Passing the proxy on explicitly stops `aiohttp` asking at all,
        which leaves only this — and this compares names, as the
        registry's own list is written in names.
        """
        import fnmatch
        import os
        import urllib.request

        listed = (os.environ.get("no_proxy") or os.environ.get("NO_PROXY")
                  or "")
        if not listed:
            try:
                import winreg

                with winreg.OpenKey(
                        winreg.HKEY_CURRENT_USER,
                        r"Software\Microsoft\Windows\CurrentVersion"
                        r"\Internet Settings") as key:
                    listed = str(winreg.QueryValueEx(key,
                                                     "ProxyOverride")[0])
            except Exception:                           # noqa: BLE001
                listed = ""
        for one in listed.replace(";", ",").split(","):
            one = one.strip().lower()
            if not one or one == "<local>":
                # `<local>` means a name with no dots in it. The
                # service has plenty.
                continue
            if one == cls.HOST or fnmatch.fnmatch(cls.HOST, one)                     or cls.HOST.endswith("." + one.lstrip(".*")):
                return True
        return False

    @staticmethod
    def _asked(voice, volume, rate):
        """The three things edge-tts wants, in the shape it wants them."""
        voice_id = (voice if voice and voice.endswith("Neural")
                    else "ru-RU-SvetlanaNeural")
        # in edge-tts, rate is given as a string of the form "+10%" / "-20%"
        pct = int(rate) - 100
        vol_pct = int(volume) - 100
        return (voice_id,
                f"{'+' if pct >= 0 else ''}{pct}%",
                f"{'+' if vol_pct >= 0 else ''}{vol_pct}%")

    def render(self, text, voice=None, volume=75, rate=100):
        edge_tts = self._try_import()
        if edge_tts is None:
            return None
        voice_id, rate_str, vol_str = self._asked(voice, volume, rate)
        try:
            import asyncio
            tmp = new_temp_file(".mp3", "rina_edge_")

            async def _gen():
                communicate = edge_tts.Communicate(
                    text, voice_id, rate=rate_str, volume=vol_str,
                    proxy=self._through())
                await communicate.save(tmp)

            asyncio.run(_gen())
            return tmp
        except Exception:
            return None

    def stream(self, text, voice=None, volume=75, rate=100):
        """
        The same speech, but given out as it arrives.

        **Why the thread.** edge-tts is asynchronous and the core's
        speech path is not; bridging by making the whole path async
        would mean rewriting everything above for the sake of one
        engine. So the event loop lives in a thread of its own and the
        pieces come over a queue — which is also the natural shape for
        "give me what you have so far".
        """
        edge_tts = self._try_import()
        if edge_tts is None:
            return
        voice_id, rate_str, vol_str = self._asked(voice, volume, rate)

        import asyncio
        import queue
        import threading

        coming = queue.Queue()
        DONE = object()

        # The engine's own half of the wait, said out loud.
        #
        # The core reports how long a reply took to start speaking, and
        # on a live machine that came out as sixteen seconds where the
        # same code measured on its own takes one. Everything between —
        # the segmentation, the decoder, the imports, the contention,
        # the name lookup — was measured and is fast. So this method
        # says its own two numbers: when the service handed the first
        # chunk over, and when anybody came to collect it. They have
        # opposite fixes, and until they were separate the sixteen
        # seconds had two plausible owners.
        import time as _time

        began = _time.monotonic()
        first = None
        chunks = 0
        through = self._through()
        #: When the service handed over the first chunk. A list because
        #: the producer runs in another thread and writes it there.
        made = [None]

        def pump():
            async def read():
                try:
                    talk = edge_tts.Communicate(text, voice_id,
                                                rate=rate_str, volume=vol_str,
                                                proxy=through)
                    async for part in talk.stream():
                        if part["type"] == "audio" and part.get("data"):
                            # When the service gave it, as against when
                            # anybody took it. Two numbers, because
                            # "sixteen seconds" has two possible owners
                            # — somebody else's service, or an
                            # interpreter too busy to come and collect —
                            # and they want opposite fixes.
                            if made[0] is None:
                                made[0] = _time.monotonic() - began
                            coming.put(part["data"])
                except Exception as trouble:            # noqa: BLE001
                    coming.put(trouble)
                finally:
                    coming.put(DONE)

            asyncio.run(read())

        worker = threading.Thread(target=pump, name="rina-edge", daemon=True)
        worker.start()
        try:
            while True:
                piece = coming.get()
                if piece is DONE:
                    return
                if isinstance(piece, Exception):
                    # Said out loud rather than swallowed: half a reply
                    # and silence about why is how a network failure
                    # looks like a broken program.
                    log.warning("Edge оборвался: %s", piece)
                    continue
                if first is None:
                    first = _time.monotonic() - began
                chunks += 1
                yield piece
        finally:
            log.info("Edge (%s): сервис отдал за %s, забрали через %s, "
                     "кусков %d, поток %d мс",
                     through or "напрямую",
                     ("%d мс" % (made[0] * 1000)) if made[0] is not None
                     else "—",
                     ("%d мс" % (first * 1000)) if first is not None
                     else "не пришёл",
                     chunks, (_time.monotonic() - began) * 1000)


class PiperEngine(TTSEngine):
    """
    Piper TTS: fast OFFLINE neural synthesis. Requires the piper-tts package
    and a downloaded voice model (.onnx). The path to the model is taken
    from the piper_model setting. Good if a local natural voice without the
    internet is wanted.
    """
    id = "piper"
    label = "Piper (офлайн, нейро)"

    def _try_import(self):
        try:
            from piper.voice import PiperVoice  # noqa
            return PiperVoice
        except Exception:
            return None

    @property
    def available(self):
        return self._try_import() is not None

    def voices(self):
        from core.settings_store import settings
        model = settings.get("piper_model", "")
        if model:
            name = os.path.basename(model)
            return [("model", f"Модель: {name}")]
        return [("model", "Модель не выбрана")]

    _voice_cache = None
    _cached_path = None

    def _load_voice(self, PiperVoice, model_path):
        # we cache the loaded model (loading is heavy)
        if self._voice_cache is not None and self._cached_path == model_path:
            return self._voice_cache
        # a .onnx.json (the config) must lie next to the .onnx. If it is
        # given without .json, piper substitutes config_path = model + ".json".
        try:
            self._voice_cache = PiperVoice.load(model_path)
        except Exception:
            # we try naming the config explicitly
            cfg = model_path + ".json"
            if os.path.isfile(cfg):
                self._voice_cache = PiperVoice.load(model_path, config_path=cfg)
            else:
                raise
        self._cached_path = model_path
        return self._voice_cache

    def render(self, text, voice=None, volume=75, rate=100):
        PiperVoice = self._try_import()
        if PiperVoice is None:
            return None
        from core.settings_store import settings
        model_path = settings.get("piper_model", "")
        if not model_path or not os.path.isfile(model_path):
            self._last_error = "Модель Piper не выбрана или файл не найден"
            return None
        import wave
        tmp = new_temp_file(".wav", "rina_piper_")
        try:
            voice_model = self._load_voice(PiperVoice, model_path)
            with wave.open(tmp, "wb") as wav:
                # the new API (piper-tts 1.x): synthesize_wav
                if hasattr(voice_model, "synthesize_wav"):
                    voice_model.synthesize_wav(text, wav)
                else:
                    # the old API: synthesize(text, wav_file)
                    voice_model.synthesize(text, wav)
            return tmp
        except Exception as e:
            # we do not swallow it in silence — we keep the reason, to show it in the UI/logs
            self._last_error = f"Ошибка Piper: {e}"
            return None
            raise


# ---------------------------------------------------------------------------
_ENGINES = None


def all_engines():
    """Every registered engine (including unavailable ones — for the UI)."""
    global _ENGINES
    if _ENGINES is None:
        _ENGINES = [SilentEngine(), Pyttsx3Engine(), EdgeTTSEngine(),
                    GttsEngine(), PiperEngine()]
    return _ENGINES


def available_engines():
    return [e for e in all_engines() if e.available]


def get_engine(engine_id):
    for e in all_engines():
        if e.id == engine_id:
            return e
    return all_engines()[0]  # SilentEngine as a safe default


def engine_choices():
    """A list of (id, label, available) for the settings dropdown."""
    return [(e.id, e.label, e.available) for e in all_engines()]
