"""
Канал данных и обратное давление.

Задачи плана `4.0-D07` (бинарный канал) и `4.0-D08` (кредитная схема);
спецификация, §2 и §8.

**Двоичные данные никогда не кодируются внутри JSON.** Base64 раздувает объём
на треть, но дело не в объёме: закодированный звук едет по управляющему
каналу и встаёт в ту же очередь, что и команды. Пока едет секунда речи,
нажатие кнопки ждёт — и это не медленный канал, а неверно устроенный.

Отсюда два канала на сессию и два разных кадра. Управляющий несёт JSON,
канал данных — байты с коротким двоичным заголовком:

    [4 байта: длина остатка кадра][4: stream_id][8: порядковый номер][байты]

Порядковый номер растёт в пределах потока и нужен для обнаружения потерь при
отладке: без него потерянный кусок звука выглядит как «Рина расслышала не всё»,
и искать причину приходится в распознавании, а не в канале.

**Кредитная схема.** Приёмник объявляет, сколько байт готов принять;
отправитель не имеет права держать в полёте больше. Начальный кредит — ноль,
то есть отправитель молчит, пока его не позовут. Без этого быстрый источник
кадров или звука переполняет очередь и утаскивает память — отказ, который
снаружи выглядит как «программа съела гигабайт», а изнутри не выглядит никак.

Начальный кредит именно ноль, а не «немного авансом»: приёмник, который ещё не
готов, не должен получать данные вовсе. Аванс превратил бы ошибку «забыли
выдать кредит» в редко воспроизводимую — она проявлялась бы только на потоках
длиннее аванса.
"""

import struct
from dataclasses import dataclass, field
from typing import Iterator

from core.wire.errors import (ERROR_FRAME_TOO_LARGE, ERROR_INVALID_PAYLOAD,
                              ERROR_INVALID_STATE, fault)

#: Предел одного кадра данных (§2). Меньше управляющего: кадр звука не обязан
#: быть большим, а мелкая нарезка даёт отзывчивость и ровное давление.
DATA_FRAME_LIMIT = 256 * 1024

#: Заголовок кадра данных после поля длины: номер потока и порядковый номер.
_HEADER = struct.Struct(">I")
_INNER = struct.Struct(">IQ")

#: Виды потоков (§8) и возможность, без которой вид не открывают.
KINDS = {
    "audio.input": "audio.input",     # микрофон, оболочка → ядро
    "audio.output": "audio.output",   # синтез, ядро → оболочка
    "screen.frame": "actuation",      # 5.0, оболочка → ядро
}


def capability_for_kind(kind: str) -> str:
    """Какую возможность собеседник обязан объявить, чтобы принять такой вид."""
    try:
        return KINDS[kind]
    except KeyError:
        raise fault(ERROR_INVALID_PAYLOAD, f"неизвестный вид потока: {kind!r}",
                    kind=kind) from None


@dataclass(frozen=True)
class DataFrame:
    stream_id: int
    seq: int
    payload: bytes


def encode_data_frame(frame: DataFrame) -> bytes:
    body = _INNER.pack(frame.stream_id, frame.seq) + frame.payload
    if len(body) > DATA_FRAME_LIMIT:
        raise fault(ERROR_FRAME_TOO_LARGE,
                    "кадр данных больше предела канала",
                    size=len(body), limit=DATA_FRAME_LIMIT)
    return _HEADER.pack(len(body)) + body


class DataFrameDecoder:
    """
    Сборка кадров данных из потока байтов.

    Предел, как и в управляющем канале, проверяется **по заявленной длине, до
    выделения памяти**: иначе он не защищает ни от чего.
    """

    def __init__(self, limit: int = DATA_FRAME_LIMIT):
        self._limit = limit
        self._buffer = bytearray()

    def feed(self, chunk: bytes) -> Iterator[DataFrame]:
        self._buffer.extend(chunk)
        while True:
            if len(self._buffer) < _HEADER.size:
                return
            (size,) = _HEADER.unpack_from(self._buffer, 0)
            if size > self._limit:
                raise fault(ERROR_FRAME_TOO_LARGE,
                            "объявленный размер кадра данных больше предела",
                            size=size, limit=self._limit)
            if size < _INNER.size:
                raise fault(ERROR_INVALID_PAYLOAD,
                            "кадр данных короче собственного заголовка",
                            size=size)
            if len(self._buffer) < _HEADER.size + size:
                return
            start = _HEADER.size
            stream_id, seq = _INNER.unpack_from(self._buffer, start)
            payload = bytes(self._buffer[start + _INNER.size:start + size])
            del self._buffer[:_HEADER.size + size]
            yield DataFrame(stream_id, seq, payload)

    @property
    def pending(self) -> int:
        return len(self._buffer)


@dataclass
class Credit:
    """
    Разрешение отправлять, выданное приёмником (§8).

    Считается в байтах, а не в кадрах: память съедают байты, и поток из
    тысячи мелких кадров ничем не лучше десяти крупных того же объёма.
    """

    granted: int = 0
    sent: int = 0

    @property
    def available(self) -> int:
        return self.granted - self.sent

    def grant(self, extra: int) -> int:
        if extra <= 0:
            raise fault(ERROR_INVALID_PAYLOAD,
                        "кредит выдаётся положительным числом байт",
                        bytes=extra)
        self.granted += extra
        return self.available

    def spend(self, size: int) -> None:
        if size > self.available:
            raise fault(ERROR_INVALID_STATE,
                        "отправитель превысил выданный кредит",
                        size=size, available=self.available)
        self.sent += size


class DataSender:
    """
    Отправляющая сторона канала данных.

    Кредит хранится **по потоку**: микрофон и синтез идут одновременно и в
    разные стороны, и общий счёт связал бы их скорости друг с другом без
    всякой на то причины.
    """

    def __init__(self):
        self._seq: dict[int, int] = {}
        self._credit: dict[int, Credit] = {}
        self.open: dict[int, str] = {}

    def open_stream(self, stream_id: int, kind: str) -> None:
        capability_for_kind(kind)          # неизвестный вид — сразу отказ
        if stream_id in self.open:
            raise fault(ERROR_INVALID_STATE, f"поток {stream_id} уже открыт",
                        stream_id=stream_id)
        self.open[stream_id] = kind
        self._seq[stream_id] = 0
        self._credit[stream_id] = Credit()

    def grant(self, stream_id: int, extra: int) -> int:
        """Приёмник прислал `stream.credit`."""
        return self._require(stream_id).grant(extra)

    def available(self, stream_id: int) -> int:
        return self._require(stream_id).available

    def send(self, stream_id: int, payload: bytes) -> bytes:
        """
        Собрать кадр, списав кредит. Кадр возвращается — отправляет вызывающий.

        Отправка без кредита — не «немного вперёд», а ошибка: приёмник,
        объявивший ноль, ещё не готов принимать вовсе.
        """
        credit = self._require(stream_id)
        credit.spend(len(payload))
        self._seq[stream_id] += 1
        return encode_data_frame(
            DataFrame(stream_id, self._seq[stream_id], payload))

    def close_stream(self, stream_id: int) -> None:
        self._require(stream_id)
        del self.open[stream_id]
        del self._seq[stream_id]
        del self._credit[stream_id]

    def _require(self, stream_id: int) -> Credit:
        if stream_id not in self.open:
            raise fault(ERROR_INVALID_STATE,
                        f"поток {stream_id} не открыт или уже закрыт",
                        stream_id=stream_id)
        return self._credit[stream_id]


class DataReceiver:
    """
    Принимающая сторона: собирает поток и следит за пропусками.

    Пропуск порядкового номера не обрывает приём. Канал не теряет кадров сам
    по себе — если пропуск случился, виновата одна из сторон, и полезнее
    записать факт с номерами, чем упасть: упавший приёмник не расскажет, где
    именно порвалось.
    """

    def __init__(self, window: int = 64 * 1024):
        self.window = window
        self._expected: dict[int, int] = {}
        self.data: dict[int, bytearray] = {}
        self.gaps: list[tuple[int, int, int]] = []
        self.consumed: dict[int, int] = {}

    def accept(self, frame: DataFrame) -> None:
        expected = self._expected.get(frame.stream_id, 0) + 1
        if frame.seq != expected:
            self.gaps.append((frame.stream_id, expected, frame.seq))
        self._expected[frame.stream_id] = frame.seq
        self.data.setdefault(frame.stream_id, bytearray()).extend(frame.payload)
        self.consumed[frame.stream_id] = (
            self.consumed.get(frame.stream_id, 0) + len(frame.payload))

    def take_credit(self, stream_id: int) -> int:
        """
        Сколько байт объявить отправителю после обработки принятого.

        Приёмник выдаёт кредит по мере обработки, а не по мере получения:
        кредит за то, что лежит необработанным в буфере, — это и есть та самая
        неограниченная очередь, ради устранения которой схема существует.
        """
        ready = self.consumed.pop(stream_id, 0)
        return min(ready, self.window) if ready else 0
