"""
The speech-to-text layer with a choice of engine and work with the
microphone.

The STTEngine abstraction:
  - SpeechRecognitionEngine — the microphone through SpeechRecognition +
                              Google (online)
  - VoskEngine              — offline recognition (needs a Vosk model)
  - DisabledEngine          — recognition switched off (listens to nothing)

Every backend is optional. Recognition blocks (it listens to the
microphone), so it is started from a background thread (voice/service.py).
"""

import os


def check_vosk_model(path):
    """
    Checks whether a folder looks like a Vosk model.

    Pointing at the wrong folder is easy (people often point at an archive
    or one level up), and without a check that comes out only at the moment
    the user says something — and the answer will be an unintelligible
    recognition error. Returns (ok, message).
    """
    import os

    from core.i18n import t as tr

    if not path:
        return False, tr("Папка модели не выбрана")
    if not os.path.isdir(path):
        return False, tr("Папки не существует")

    names = set(os.listdir(path))
    # every Vosk model has an acoustic part and a config
    required = ("am", "conf")
    missing = [n for n in required if n not in names]
    if missing:
        # a common case: a folder one level above the real model was named
        nested = [n for n in names
                  if os.path.isdir(os.path.join(path, n))
                  and {"am", "conf"} <= set(os.listdir(os.path.join(path, n)))]
        if nested:
            return False, tr("Похоже, модель лежит внутри: {name}",
                             name=nested[0])
        return False, tr("Не похоже на модель Vosk (нет папок am/conf)")
    return True, tr("Модель Vosk на месте")


def check_piper_model(path):
    """Checks a Piper voice file (.onnx plus a config beside it)."""
    import os

    from core.i18n import t as tr

    if not path:
        return False, tr("Файл модели не выбран")
    if not os.path.isfile(path):
        return False, tr("Файла не существует")
    if not path.lower().endswith(".onnx"):
        return False, tr("Нужен файл .onnx")
    if not os.path.isfile(path + ".json"):
        return False, tr("Рядом нет файла настроек .onnx.json")
    return True, tr("Модель Piper на месте")


class STTResult:
    def __init__(self, text="", ok=False, error=None):
        self.text = text
        self.ok = ok
        self.error = error


class STTEngine:
    id = "base"
    label = "Base"

    @property
    def available(self):
        return False

    def listen_once(self, language="ru", timeout=6) -> STTResult:
        """Listens to the microphone once and returns the recognised text."""
        raise NotImplementedError


# ---------------------------------------------------------------------------
class DisabledEngine(STTEngine):
    """
    Recognition is switched off. Listens to NOTHING and gives out NO
    phrases — so the assistant does not react "by itself". Chosen by default
    until the user installs a real engine (Google/Vosk).
    """
    id = "disabled"
    label = "Выключено (нет распознавания)"

    @property
    def available(self):
        return True

    def listen_once(self, language="ru", timeout=6) -> STTResult:
        return STTResult(
            ok=False,
            error="Распознавание речи выключено. Выберите движок STT "
                  "в настройках (нужен микрофон и библиотека).")


# ---------------------------------------------------------------------------
def _sd_available():
    try:
        import sounddevice  # noqa
        import numpy  # noqa
        return True
    except Exception:
        return False


def _record_sounddevice(seconds=6, samplerate=16000):
    """
    Records audio from the microphone through sounddevice (without PyAudio).
    Returns (numpy_float32_mono, samplerate), or (None, sr) on an error.
    Takes the chosen input device from the settings into account.

    The audio is cleaned of NaN/inf: broken samples (the device gave less
    data than it should, a wrong format) otherwise cause warnings and
    rubbish in the recognition.
    """
    try:
        import sounddevice as sd
        import numpy as np
        from core.settings_store import settings
        device_id = settings.get("input_device", "default")
        kwargs = {}
        if device_id and device_id != "default":
            try:
                kwargs["device"] = int(device_id)
            except ValueError:
                pass
        frames = int(seconds * samplerate)
        rec = sd.rec(frames, samplerate=samplerate, channels=1,
                     dtype="float32", **kwargs)
        sd.wait()
        data = rec.flatten()

        # we clean NaN/inf: broken samples (the device gave less data than
        # it should, a wrong format) otherwise cause warnings and rubbish in
        # the recognition.
        had_bad = not np.all(np.isfinite(data))
        data = np.nan_to_num(data, nan=0.0, posinf=0.0, neginf=0.0)
        data = data.astype(np.float32, copy=False)

        # if the WHOLE recording was broken (nothing but NaN/inf) — that is a device failure
        if had_bad and not np.any(np.abs(data) > 1e-5):
            return None, samplerate

        return data, samplerate
    except Exception:
        return None, samplerate


def _to_pcm16(data):
    """float32 [-1..1] -> int16 little-endian PCM (bytes), safe against NaN/inf."""
    import numpy as np
    arr = np.asarray(data, dtype=np.float32)
    # NaN -> 0, +inf -> +1 (the rail), -inf -> -1 (the rail), then clipped to [-1,1]
    arr = np.nan_to_num(arr, nan=0.0, posinf=1.0, neginf=-1.0)
    arr = np.clip(arr, -1.0, 1.0)
    return (arr * 32767.0).astype("<i2").tobytes()


class SpeechRecognitionEngine(STTEngine):
    """
    Online Google recognition through SpeechRecognition.
    Capture is through sounddevice (needs no PyAudio), then the audio is
    handed to the recognizer. Works with whatever installation you have.
    """
    id = "google"
    label = "Google (онлайн, микрофон)"

    _LANG = {"ru": "ru-RU", "en": "en-US", "uk": "uk-UA",
             "es": "es-ES", "de": "de-DE"}

    def _try_import(self):
        try:
            import speech_recognition as sr  # noqa
            return sr
        except Exception:
            return None

    @property
    def available(self):
        return self._try_import() is not None and _sd_available()

    def listen_once(self, language="ru", timeout=6) -> STTResult:
        sr = self._try_import()
        if sr is None:
            return STTResult(error="Установите SpeechRecognition")
        if not _sd_available():
            return STTResult(error="Установите sounddevice и numpy")
        data, samplerate = _record_sounddevice(seconds=max(4, timeout))
        if data is None:
            return STTResult(error="Не удалось записать с микрофона")
        try:
            import numpy as np
            # float32 -> int16 PCM for sr.AudioData
            pcm = _to_pcm16(data)
            audio = sr.AudioData(pcm, samplerate, 2)
            recognizer = sr.Recognizer()
            lang = self._LANG.get(language, "ru-RU")
            text = recognizer.recognize_google(audio, language=lang)
            if not text.strip():
                return STTResult(error="Не удалось распознать речь")
            return STTResult(text=text, ok=True)
        except sr.UnknownValueError:
            return STTResult(error="Не удалось распознать речь")
        except Exception as e:
            return STTResult(error=f"Ошибка распознавания: {e}")


# ---------------------------------------------------------------------------
class VoskEngine(STTEngine):
    """
    Offline Vosk recognition. Needs a downloaded model (a folder); the path
    is in the vosk_model setting. Capture is through sounddevice.
    Models: https://alphacephei.com/vosk/models (e.g. vosk-model-small-ru).
    """
    id = "vosk"
    label = "Vosk (офлайн, микрофон)"

    _model = None
    _model_path = None

    def _try_import(self):
        try:
            import vosk  # noqa
            return vosk
        except Exception:
            return None

    @property
    def available(self):
        return self._try_import() is not None and _sd_available()

    def _get_model(self):
        from core.settings_store import settings
        vosk = self._try_import()
        if vosk is None:
            return None
        path = settings.get("vosk_model", "")
        if not path or not os.path.isdir(path):
            return None
        # we cache the model between calls
        if self._model is None or self._model_path != path:
            try:
                self._model = vosk.Model(path)
                self._model_path = path
            except Exception:
                self._model = None
        return self._model

    def listen_once(self, language="ru", timeout=6) -> STTResult:
        vosk = self._try_import()
        if vosk is None:
            return STTResult(error="Установите vosk (pip install vosk)")
        if not _sd_available():
            return STTResult(error="Установите sounddevice и numpy")
        model = self._get_model()
        if model is None:
            return STTResult(
                error="Модель Vosk не выбрана. Скачайте модель и укажите путь "
                      "в настройке (vosk_model).")
        data, samplerate = _record_sounddevice(seconds=max(4, timeout))
        if data is None:
            return STTResult(error="Не удалось записать с микрофона")
        try:
            import json
            import numpy as np
            rec = vosk.KaldiRecognizer(model, samplerate)
            pcm = _to_pcm16(data)
            rec.AcceptWaveform(pcm)
            result = json.loads(rec.FinalResult())
            text = result.get("text", "").strip()
            if not text:
                return STTResult(error="Не удалось распознать речь")
            return STTResult(text=text, ok=True)
        except Exception as e:
            return STTResult(error=f"Ошибка Vosk: {e}")


# ---------------------------------------------------------------------------
class WhisperEngine(STTEngine):
    """
    Offline OpenAI Whisper recognition (locally). Requires the
    openai-whisper package. Accurate but heavy; the model's size is the
    whisper_model setting (tiny/base/small/medium). Capture is through
    sounddevice.
    """
    id = "whisper"
    label = "Whisper (офлайн, точный)"

    _model = None
    _model_size = None

    def _try_import(self):
        try:
            import whisper  # noqa
            return whisper
        except Exception:
            return None

    @property
    def available(self):
        return self._try_import() is not None and _sd_available()

    def _get_model(self):
        from core.settings_store import settings
        whisper = self._try_import()
        if whisper is None:
            return None
        size = settings.get("whisper_model", "base")
        if self._model is None or self._model_size != size:
            try:
                self._model = whisper.load_model(size)
                self._model_size = size
            except Exception:
                self._model = None
        return self._model

    def listen_once(self, language="ru", timeout=6) -> STTResult:
        whisper = self._try_import()
        if whisper is None:
            return STTResult(error="Установите openai-whisper")
        if not _sd_available():
            return STTResult(error="Установите sounddevice и numpy")
        model = self._get_model()
        if model is None:
            return STTResult(error="Не удалось загрузить модель Whisper")
        data, samplerate = _record_sounddevice(seconds=max(4, timeout))
        if data is None:
            return STTResult(error="Не удалось записать с микрофона")
        try:
            import numpy as np
            # whisper expects float32 16 kHz mono — which is what we have
            audio = np.nan_to_num(data.astype(np.float32), nan=0.0, posinf=0.0, neginf=0.0)
            result = model.transcribe(audio, language=language, fp16=False)
            text = (result.get("text") or "").strip()
            if not text:
                return STTResult(error="Не удалось распознать речь")
            return STTResult(text=text, ok=True)
        except Exception as e:
            return STTResult(error=f"Ошибка Whisper: {e}")


# ---------------------------------------------------------------------------
class SphinxEngine(STTEngine):
    """
    Offline CMU PocketSphinx recognition through SpeechRecognition.
    Entirely local, without downloading models by hand (for English; other
    languages need language packs). Capture is through sounddevice.
    """
    id = "sphinx"
    label = "PocketSphinx (офлайн)"

    def _try_import(self):
        try:
            import speech_recognition as sr  # noqa
            import pocketsphinx  # noqa
            return sr
        except Exception:
            return None

    @property
    def available(self):
        return self._try_import() is not None and _sd_available()

    def listen_once(self, language="ru", timeout=6) -> STTResult:
        sr = self._try_import()
        if sr is None:
            return STTResult(error="Установите SpeechRecognition и pocketsphinx")
        if not _sd_available():
            return STTResult(error="Установите sounddevice и numpy")
        data, samplerate = _record_sounddevice(seconds=max(4, timeout))
        if data is None:
            return STTResult(error="Не удалось записать с микрофона")
        try:
            import numpy as np
            pcm = _to_pcm16(data)
            audio = sr.AudioData(pcm, samplerate, 2)
            recognizer = sr.Recognizer()
            text = recognizer.recognize_sphinx(audio)
            if not text.strip():
                return STTResult(error="Не удалось распознать речь")
            return STTResult(text=text, ok=True)
        except Exception as e:
            return STTResult(error=f"Ошибка Sphinx: {e}")


# ---------------------------------------------------------------------------
_ENGINES = None


def all_engines():
    global _ENGINES
    if _ENGINES is None:
        _ENGINES = [DisabledEngine(), SpeechRecognitionEngine(), VoskEngine(),
                    WhisperEngine(), SphinxEngine()]
    return _ENGINES


def available_engines():
    return [e for e in all_engines() if e.available]


def get_engine(engine_id):
    for e in all_engines():
        if e.id == engine_id:
            return e
    return all_engines()[0]  # DisabledEngine as a safe default


def engine_choices():
    return [(e.id, e.label, e.available) for e in all_engines()]
