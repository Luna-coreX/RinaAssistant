"""
Speech-to-Text слой с выбором движка и работой с микрофоном.

Абстракция STTEngine:
  - SpeechRecognitionEngine — микрофон через SpeechRecognition + Google (онлайн)
  - VoskEngine              — офлайн распознавание (нужна модель Vosk)
  - DisabledEngine          — распознавание выключено (ничего не слушает)

Каждый бэкенд опционален. Распознавание блокирующее (слушает микрофон),
поэтому запускается из фонового потока (voice/service.py).
"""

import threading


def check_vosk_model(path):
    """
    Проверяет, похожа ли папка на модель Vosk.

    Ошибиться папкой легко (часто указывают на архив или на уровень выше),
    и без проверки это выясняется только в момент, когда пользователь
    что-то сказал, — а ответом будет невнятная ошибка распознавания.
    Возвращает (ok, сообщение).
    """
    import os

    from core.i18n import t as tr

    if not path:
        return False, tr("Папка модели не выбрана")
    if not os.path.isdir(path):
        return False, tr("Папки не существует")

    names = set(os.listdir(path))
    # у любой модели Vosk есть акустическая часть и конфиг
    required = ("am", "conf")
    missing = [n for n in required if n not in names]
    if missing:
        # частый случай: указали папку на уровень выше настоящей модели
        nested = [n for n in names
                  if os.path.isdir(os.path.join(path, n))
                  and {"am", "conf"} <= set(os.listdir(os.path.join(path, n)))]
        if nested:
            return False, tr("Похоже, модель лежит внутри: {name}",
                             name=nested[0])
        return False, tr("Не похоже на модель Vosk (нет папок am/conf)")
    return True, tr("Модель Vosk на месте")


def check_piper_model(path):
    """Проверяет файл голоса Piper (.onnx + конфиг рядом)."""
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
        """Слушает микрофон один раз и возвращает распознанный текст."""
        raise NotImplementedError


# ---------------------------------------------------------------------------
class DisabledEngine(STTEngine):
    """
    Распознавание выключено. Ничего НЕ слушает и НЕ выдаёт фраз — поэтому
    ассистент не реагирует «сам по себе». Выбирается по умолчанию, пока
    пользователь не установит реальный движок (Google/Vosk).
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
    Записывает аудио с микрофона через sounddevice (без PyAudio).
    Возвращает (numpy_float32_mono, samplerate) или (None, sr) при ошибке.
    Учитывает выбранное устройство ввода из настроек.

    Аудио очищается от NaN/inf: битые сэмплы (устройство недодало данные,
    неверный формат) иначе вызывают предупреждения и мусор в распознавании.
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

        # чистим NaN/inf: битые сэмплы (устройство недодало данные, неверный
        # формат) иначе вызывают предупреждения и мусор в распознавании.
        had_bad = not np.all(np.isfinite(data))
        data = np.nan_to_num(data, nan=0.0, posinf=0.0, neginf=0.0)
        data = data.astype(np.float32, copy=False)

        # если ВСЯ запись была битой (сплошь NaN/inf) — это сбой устройства
        if had_bad and not np.any(np.abs(data) > 1e-5):
            return None, samplerate

        return data, samplerate
    except Exception:
        return None, samplerate


def _to_pcm16(data):
    """float32 [-1..1] -> int16 little-endian PCM (bytes), безопасно к NaN/inf."""
    import numpy as np
    arr = np.asarray(data, dtype=np.float32)
    # NaN -> 0, +inf -> +1 (рейл), -inf -> -1 (рейл), затем клип в [-1,1]
    arr = np.nan_to_num(arr, nan=0.0, posinf=1.0, neginf=-1.0)
    arr = np.clip(arr, -1.0, 1.0)
    return (arr * 32767.0).astype("<i2").tobytes()


class SpeechRecognitionEngine(STTEngine):
    """
    Онлайн-распознавание Google через SpeechRecognition.
    Захват — через sounddevice (не требует PyAudio), затем аудио передаётся
    в recognizer. Работает с той установкой, что у вас есть.
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
            # float32 -> int16 PCM для sr.AudioData
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
    Офлайн-распознавание Vosk. Нужна скачанная модель (папка), путь — в
    настройке vosk_model. Захват через sounddevice.
    Модели: https://alphacephei.com/vosk/models (напр. vosk-model-small-ru).
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
        # кэшируем модель между вызовами
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
    Офлайн-распознавание OpenAI Whisper (локально). Требует пакет
    openai-whisper. Точный, но тяжёлый; размер модели — настройка whisper_model
    (tiny/base/small/medium). Захват через sounddevice.
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
            # whisper ждёт float32 16кГц mono — у нас уже так
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
    Офлайн-распознавание CMU PocketSphinx через SpeechRecognition.
    Полностью локальное, без скачивания моделей вручную (для английского;
    для других языков нужны языковые пакеты). Захват через sounddevice.
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
    return all_engines()[0]  # DisabledEngine как безопасный дефолт


def engine_choices():
    return [(e.id, e.label, e.available) for e in all_engines()]
