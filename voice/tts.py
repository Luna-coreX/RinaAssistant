"""
Text-to-Speech слой с выбором движка.

Абстракция TTSEngine позволяет выбирать «саму TTS» (не только голос):
  - Pyttsx3Engine   — офлайн, системный синтез (SAPI5/NSSS/espeak)
  - GttsEngine      — онлайн, Google TTS (естественнее, нужен интернет)
  - SilentEngine    — без озвучки (только toast/текст), всегда доступен

Каждый бэкенд опционален: если библиотека не установлена, движок помечается
недоступным (available=False) и не предлагается. SilentEngine есть всегда,
поэтому приложение работает и без единой TTS-библиотеки.

Синтез блокирующий, поэтому вызывается из фонового потока (см. voice/service.py),
а не напрямую из GUI.

Воспроизведение проходит через единственную очередь (_Playback): ответы
звучат по одному и в порядке поступления. Каждый синтез пишет в собственный
временный файл, который удаляется после проигрывания.
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
        """Список (voice_id, human_label) доступных голосов."""
        return []

    def render(self, text, voice=None, volume=75, rate=100):
        """
        Синтезировать в файл и вернуть путь. `None` — не вышло.

        Появилось для 4.0: синтез в ядре, воспроизведение в оболочке
        (`4.0-F10`). Движку и раньше приходилось делать файл — каждый писал
        временный и тут же его проигрывал; разделение лишь называет этот шаг
        вслух. Кто вызвал, тот и удаляет.
        """
        return None

    def speak(self, text, voice=None, volume=75, rate=100):
        """Блокирующе произносит текст. rate/volume — проценты (100 = норма)."""
        path = self.render(text, voice=voice, volume=volume, rate=rate)
        if path:
            _play_audio_file(path, delete_after=True)

    def stop(self):
        pass


# ---------------------------------------------------------------------------
class SilentEngine(TTSEngine):
    """Ничего не озвучивает — только текст/toast. Всегда доступен."""
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
        # намеренно тихо; небольшая пауза ~ время «произношения»
        return


# ---------------------------------------------------------------------------
class Pyttsx3Engine(TTSEngine):
    """Офлайн системный TTS через pyttsx3."""
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
        # pyttsx3 rate ~ слов/мин; 200 ≈ норма. Масштабируем от rate%.
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
        # Произносит сам, а не через файл: системный синтез это умеет, и
        # лишний круг через диск добавил бы задержку там, где её нет.
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
    """Онлайн Google TTS (естественный голос, нужен интернет)."""
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
        # воспроизведение через sounddevice + soundfile (как у Edge/Piper)
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
    """Индекс выбранного устройства вывода или None (по умолчанию)."""
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
    Отдельный файл под каждый синтез.

    Раньше имена были постоянными («rina_gtts.mp3»), и два ответа подряд
    затирали файл друг друга: первый обрывался на середине, второй мог
    прочитать наполовину записанные данные.
    """
    fd, path = tempfile.mkstemp(prefix=prefix, suffix=suffix)
    os.close(fd)            # писать будет синтезатор, ему нужен путь
    return path


class _Playback:
    """
    Единственный воркер воспроизведения.

    Ответы Рины должны звучать по очереди и целиком. Без очереди два
    синтеза, начавшиеся почти одновременно, играли одновременно: слышно
    было обоих и ни одного.
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
                # сбой одного файла не должен уносить воркер: следующий
                # ответ обязан прозвучать
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
        """Ставит файл в очередь. При wait=True ждёт окончания."""
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
    """Поставить файл в очередь воспроизведения и дождаться его."""
    return _playback.play(path, delete_after=delete_after, wait=True)


def _play_now(path):
    """Собственно воспроизведение. Вызывается только воркером очереди."""
    device = _selected_output_device()

    # если выбрано конкретное устройство вывода — играем через sounddevice,
    # т.к. только он умеет направлять звук на заданное устройство.
    if device is not None:
        try:
            import soundfile as sf
            import sounddevice as sd
            data, sr = sf.read(path, dtype="float32")
            sd.play(data, sr, device=device)
            sd.wait()
            return True
        except Exception:
            pass  # не вышло — падаем на общие способы ниже

    # 1) playsound (лёгкий, системный вывод по умолчанию)
    try:
        import playsound
        playsound.playsound(path, True)
        return True
    except Exception:
        pass
    # 2) sounddevice + soundfile (то, что уже стоит для микрофона)
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
    # 3) системный проигрыватель как крайний случай
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
    Microsoft Edge Neural TTS (edge-tts): бесплатно, онлайн, очень естественные
    нейросетевые голоса. Требует пакет edge-tts. Это отличный вариант «по
    умолчанию» для качественной озвучки без ключей.
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

    def render(self, text, voice=None, volume=75, rate=100):
        edge_tts = self._try_import()
        if edge_tts is None:
            return None
        voice_id = voice if voice and voice.endswith("Neural") else "ru-RU-SvetlanaNeural"
        # rate в edge-tts задаётся строкой вида "+10%" / "-20%"
        pct = int(rate) - 100
        rate_str = f"{'+' if pct >= 0 else ''}{pct}%"
        vol_pct = int(volume) - 100
        vol_str = f"{'+' if vol_pct >= 0 else ''}{vol_pct}%"
        try:
            import asyncio
            tmp = new_temp_file(".mp3", "rina_edge_")

            async def _gen():
                communicate = edge_tts.Communicate(
                    text, voice_id, rate=rate_str, volume=vol_str)
                await communicate.save(tmp)

            asyncio.run(_gen())
            return tmp
        except Exception:
            return None


class PiperEngine(TTSEngine):
    """
    Piper TTS: быстрый ОФЛАЙН нейросинтез. Требует пакет piper-tts и скачанную
    модель голоса (.onnx). Путь к модели берётся из настройки piper_model.
    Хорош, если нужен локальный естественный голос без интернета.
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
        # кэшируем загруженную модель (загрузка тяжёлая)
        if self._voice_cache is not None and self._cached_path == model_path:
            return self._voice_cache
        # рядом с .onnx должен лежать .onnx.json (конфиг). Если указан без .json —
        # piper сам подставит config_path = model + ".json".
        try:
            self._voice_cache = PiperVoice.load(model_path)
        except Exception:
            # пробуем явно указать конфиг
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
                # новый API (piper-tts 1.x): synthesize_wav
                if hasattr(voice_model, "synthesize_wav"):
                    voice_model.synthesize_wav(text, wav)
                else:
                    # старый API: synthesize(text, wav_file)
                    voice_model.synthesize(text, wav)
            return tmp
        except Exception as e:
            # не глушим молча — сохраняем причину, чтобы показать в UI/логах
            self._last_error = f"Ошибка Piper: {e}"
            return None
            raise


# ---------------------------------------------------------------------------
_ENGINES = None


def all_engines():
    """Все зарегистрированные движки (в т.ч. недоступные — для UI)."""
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
    return all_engines()[0]  # SilentEngine как безопасный дефолт


def engine_choices():
    """Список (id, label, available) для выпадающего списка настроек."""
    return [(e.id, e.label, e.available) for e in all_engines()]
