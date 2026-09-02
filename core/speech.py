# -*- coding: utf-8 -*-
"""
Речь в ядре: распознать присланное, синтезировать отвечаемое.

Задачи плана `4.0-E03` (распознавание) и `4.0-E04` (синтез).

**Что здесь меняется по сравнению с 3.1.0.** Там движки распознавания сами
писали с микрофона (`listen_once`), а движки синтеза сами играли звук
(`speak`). В разделённой программе и то и другое принадлежит оболочке: у неё
устройства и низкая задержка. Ядру остаётся то, ради чего оно и ядро, —
модели.

Отсюда две новые границы, и обе узкие:

    Recogniser    байты PCM  ->  текст
    Synthesiser   текст      ->  байты PCM

Ни одна из них не знает ни про устройства, ни про каналы. Это позволяет
проверить их синтетическим звуком, а заодно означает, что распознать можно и
запись из файла — например, разбирая жалобу.

**Микрофон приходит в 16 кГц, моно, 16 бит** — том формате, что понимают и
Vosk, и Whisper, и в котором оболочка захватывает (`4.0-F09`).

**Синтез объявляет свою частоту, а не подгоняется.** Модели говорят на
разных: у поля `format` в `stream.open` (§8) ровно это назначение. Пересчёт
без фильтра даёт призвуки, а с фильтром — это работа ради того, чтобы не
заполнить одно поле.

**Нарезка на фразы живёт здесь, а не в оболочке.** Оболочка считает уровень
для полосы прибора, но решение «речь кончилась» принимается рядом с
распознаванием: только здесь известно, сколько тишины считать паузой в
предложении, а сколько — концом фразы, и это зависит от модели.
"""

import array
import math
import struct
from typing import Protocol

#: Формат, в котором звук ходит между оболочкой и ядром.
RATE = 16000
CHANNELS = 1
BITS = 16
SAMPLE_BYTES = 2


class Heard:
    """Что услышали. Пустой текст при `ok` значит «тишина, но всё в порядке»."""

    __slots__ = ("text", "ok", "error")

    def __init__(self, text="", ok=True, error=""):
        self.text = text
        self.ok = ok
        self.error = error

    def __repr__(self):
        return f"Heard({self.text!r}, ok={self.ok}, error={self.error!r})"


class Segmenter:
    """
    Режет непрерывный поток на фразы по тишине.

    Простой энергетический порог с задержкой отпускания — не потому, что
    лучше нейросетевого, а потому, что честнее: настоящий VAD появится в
    5.0 вместе со стримингом, а до тех пор притворяться, что он есть,
    незачем.

    **Задержка отпускания обязательна.** Без неё фраза рвётся на каждой
    паузе между словами: «поставь… таймер» превращается в две фразы, и
    вторая приходит без первой. Полсекунды тишины — это пауза, полторы —
    конец фразы.

    **Начало фразы не теряется.** Кусок, на котором звук впервые превысил
    порог, уже содержит начало слова, поэтому в фразу он входит целиком, а
    не с того места, где сработал порог.
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
        Среднеквадратичная громкость 0..1.

        Считается вручную, а не `audioop.rms`: модуль объявлен устаревшим и
        **удалён в Python 3.13**. Ядро переживёт эту версию, и обнаружить
        такое при обновлении интерпретатора — худший момент из возможных.
        Считать здесь нечего: полторы тысячи образцов на кусок.
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
        """Принять кусок и вернуть завершившиеся фразы."""
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
            # Тишина внутри фразы всё равно записывается: вырезать её значит
            # склеить слова и получить «поставьтаймер».
            self._buffer.extend(pcm)
            self._quiet += seconds
            if self._quiet >= self.silence:
                phrase = self.flush()
                if phrase is not None:
                    done.append(phrase)

        if self._speaking and self._speech >= self.max_speech:
            # Слишком длинная фраза — не повод копить бесконечно: человек мог
            # оставить микрофон у работающего телевизора.
            phrase = self.flush()
            if phrase is not None:
                done.append(phrase)
        return done

    def flush(self) -> bytes | None:
        """Закончить фразу принудительно. `None` — там нечего слушать."""
        phrase = bytes(self._buffer)
        speech = self._speech
        self._buffer.clear()
        self._quiet = self._speech = 0.0
        self._speaking = False
        if speech < self.min_speech:
            return None
        return phrase


# ---------------------------------------------------------------------------
# Распознавание (4.0-E03)
# ---------------------------------------------------------------------------
class Recogniser(Protocol):
    """Байты PCM на входе, текст на выходе."""

    name: str

    def available(self) -> bool: ...

    def recognise(self, pcm: bytes, language: str = "ru") -> Heard: ...


class DisabledRecogniser:
    """
    Распознавания нет, и об этом говорится прямо.

    Молчаливое «ничего не услышала» здесь было бы худшим ответом: человек
    решил бы, что его не слышно, и стал бы говорить громче.
    """

    name = "disabled"

    def available(self) -> bool:
        return False

    def recognise(self, pcm: bytes, language: str = "ru") -> Heard:
        return Heard(ok=False, error="stt.unavailable")


class VoskRecogniser:
    """
    Vosk по присланным байтам, без микрофона.

    Vosk умеет принимать поток кусками, и это ровно то, что нужно: звук
    приходит от оболочки по каналу данных, а не с устройства. Модель
    держится открытой между фразами — её загрузка занимает секунды.
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
    """Какое распознавание выбрано в настройках."""
    engine = str(settings.get("stt_engine", "disabled") or "disabled")
    if engine == "vosk":
        return VoskRecogniser(str(settings.get("vosk_model", "") or ""))
    return DisabledRecogniser()


# ---------------------------------------------------------------------------
# Синтез (4.0-E04)
# ---------------------------------------------------------------------------
class Synthesiser(Protocol):
    """
    Текст на входе, байты PCM на выходе.

    `sample_rate` объявляется, а не подразумевается: разные модели говорят
    на разных частотах, и поле `format` в `stream.open` существует ровно для
    того, чтобы об этом сказать, а не догадываться.
    """

    name: str
    sample_rate: int

    def available(self) -> bool: ...

    def synthesize(self, text: str, voice: str = "", rate: int = 100) -> bytes: ...


class SilentSynthesiser:
    """Синтеза нет: ответ остаётся текстом. Это законный режим, а не поломка."""

    name = "silent"
    sample_rate = RATE

    def available(self) -> bool:
        return False

    def synthesize(self, text: str, voice: str = "", rate: int = 100) -> bytes:
        return b""


class PiperSynthesiser:
    """
    Piper: свой голос Рины, локально.

    Отдаёт сырые образцы, а не файл: файл пришлось бы записать на диск,
    прочитать и удалить — три операции ради того, что и так уже в памяти.
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
        Частота, в которой говорит модель.

        Не пересчитывается к частоте микрофона: у потока данных есть поле
        `format` (§8), и объявить свою частоту дешевле и честнее, чем
        пересчитывать. Пересчёт без фильтра даёт призвуки, а с фильтром —
        это работа, которую делают ради того, чтобы не заполнить одно поле.
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
    Прочитать звуковой файл как PCM 16 бит моно. Возвращает байты и частоту.

    Движки 3.1.0 отдают файл — mp3 у сетевых, wav у системных, — а провод
    несёт сырые образцы (§8). Пересчёта частоты здесь нет намеренно: она
    объявляется в `format` при открытии потока, и сказать «я говорю на
    24000» дешевле и честнее, чем пересчитывать без фильтра.
    """
    try:
        import numpy
        import soundfile

        data, rate = soundfile.read(path, dtype="int16", always_2d=True)
        # Моно: провод и динамик оболочки договорились об одном канале.
        # Смешивать в int16 нельзя — переполнится; считаем в широком типе.
        if data.shape[1] > 1:
            data = data.mean(axis=1).astype(numpy.int16)
        else:
            data = data[:, 0]
        return data.tobytes(), int(rate)
    except Exception:                                   # noqa: BLE001
        pass

    # Запасной путь без сторонних пакетов — только для wav. Сетевые движки
    # отдают mp3, и для них soundfile обязателен; сказать об этом честнее,
    # чем молча промолчать голосом.
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
    Синтез движками 3.1.0: edge, gtts, pyttsx3, piper.

    Движки писались под «сказать вслух здесь же»: каждый делал временный
    файл и сам его проигрывал. В 4.0 играет оболочка, поэтому берётся файл
    (`TTSEngine.render`), а не звук из динамика ядра. Ядро без оболочки
    молчит — и это верно: у процесса, который может работать сервисом, не
    должно быть своего голоса.

    Своего класса на каждый движок здесь нет: разница между ними —
    внутри `voice/tts.py`, а для ядра все они одно и то же — текст на входе,
    файл на выходе. Второй список движков разошёлся бы с первым.
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
        """Частота последнего синтеза; до первого — частота микрофона."""
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
            # Временный файл — наш: движок его создал по нашей просьбе.
            if path:
                try:
                    os.remove(path)
                except OSError:
                    pass


def synthesiser_for(settings) -> Synthesiser:
    """
    Какой синтез выбран в настройках.

    Раньше здесь узнавался один Piper, а всё остальное молча становилось
    тишиной: человек выбирал Edge, ядро отвечало текстом и не говорило.
    Молчание вместо голоса — худший вид отказа, потому что выглядит как
    работающая программа.
    """
    engine = str(settings.get("tts_engine", "silent") or "silent")
    if engine in ("", "silent"):
        return SilentSynthesiser()
    if engine == "piper" and settings.get("piper_model"):
        # Своя дорога: Piper отдаёт образцы прямо в память, без файла.
        return PiperSynthesiser(str(settings.get("piper_model", "") or ""))
    return EngineSynthesiser(engine, settings)


# ---------------------------------------------------------------------------
# Общее
# ---------------------------------------------------------------------------
def tone(seconds: float, hertz: float = 440.0, rate: int = RATE) -> bytes:
    """
    Синтетический звук для проверок.

    Живёт в ядре, а не в тесте, потому что нужен обеим сторонам: тест ядра
    проверяет им нарезку, тест оболочки — очередь воспроизведения, и две
    копии одной синусоиды разошлись бы по громкости.
    """
    samples = int(rate * seconds)
    return b"".join(
        struct.pack("<h", int(math.sin(2 * math.pi * hertz * i / rate) * 12000))
        for i in range(samples))


def silence(seconds: float, rate: int = RATE) -> bytes:
    return b"\x00" * (int(rate * seconds) * SAMPLE_BYTES)
