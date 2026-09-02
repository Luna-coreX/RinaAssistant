"""
Конверт сообщения и кадрирование управляющего канала.

Задача плана `4.0-D04`; спецификация, §2 и §3.

В 3.1.0 конверта не было вовсе: событие несло только полезную нагрузку, и
связать нажатие в окне с тем, что произошло в ядре, было нечем — потому что
всё происходило в одном процессе и связывать было незачем. В двух процессах
это перестаёт работать, и конверт — цена, которую платят за разделение.

**Поля конверта присутствуют в каждом сообщении без исключений.** Слово
«исключений нет» здесь не риторика: конверт, который иногда неполон, требует
проверки на каждой стороне у каждого получателя, и одна из этих проверок
однажды будет забыта.

**Неизвестные поля конверта пропускаются молча.** Это ровно обратное правилу
реестра инструментов, где лишний аргумент — ошибка (`core/tools.py`), и
разница не в аккуратности, а в том, кто с кем разговаривает. Внутри процесса
вызывающий и вызываемый собраны вместе: лишний аргумент значит, что кто-то
ошибся прямо сейчас. Через границу версий стороны собраны порознь, и правила
совместимости (§4) прямо разрешают добавлять необязательное поле, не меняя
версию протокола. Получатель, спотыкающийся о незнакомое поле, превращает это
разрешение в ложь и делает ступенчатое обновление невозможным.
"""

import json
import struct
import time
from dataclasses import dataclass, field
from typing import Any, Iterator

from core.wire.errors import (ERROR_FRAME_TOO_LARGE, ERROR_INVALID_ENVELOPE,
                              fault)
from core.wire.trace import new_trace_id, require_trace

#: Предел одного управляющего сообщения (§2). Больше — дефект или попытка
#: исчерпать память, и то и другое лечится разрывом, а не разбором.
CONTROL_FRAME_LIMIT = 1024 * 1024

#: Длина префикса кадра: 4 байта, big-endian, без знака.
_HEADER = struct.Struct(">I")

PROTOCOL_VERSION = 1


class MessageType:
    REQUEST = "request"
    RESPONSE = "response"
    EVENT = "event"
    ERROR = "error"


ALL_TYPES = (MessageType.REQUEST, MessageType.RESPONSE,
             MessageType.EVENT, MessageType.ERROR)

#: Какие поля обязательны сверх общих, в зависимости от типа сообщения (§3).
#: Запрос и событие обязаны назвать метод; ответ и ошибка — сказать, на что
#: они отвечают. Ответ без `correlation_id` неотличим от события и потому
#: бесполезен.
_EXTRA_REQUIRED = {
    MessageType.REQUEST: ("method",),
    MessageType.EVENT: ("method",),
    MessageType.RESPONSE: ("correlation_id",),
    MessageType.ERROR: ("correlation_id",),
}


@dataclass(frozen=True)
class Envelope:
    """
    Одно сообщение управляющего канала.

    Замороженный: сообщение, побывавшее в журнале и в трассировке, не должно
    отличаться от того, что ушло в канал.
    """

    type: str
    id: str
    timestamp: float
    trace_id: str
    payload: dict[str, Any] = field(default_factory=dict)
    v: int = PROTOCOL_VERSION
    method: str | None = None
    correlation_id: str | None = None
    stream_id: int | None = None

    def __post_init__(self):
        _validate(self.type, self.id, self.v, self.timestamp, self.trace_id,
                  self.method, self.correlation_id, self.stream_id,
                  self.payload)

    def to_dict(self) -> dict[str, Any]:
        """Словарь для сериализации: необязательные поля опускаются."""
        out: dict[str, Any] = {
            "v": self.v,
            "type": self.type,
            "id": self.id,
            "timestamp": self.timestamp,
            "trace_id": self.trace_id,
            "payload": dict(self.payload),
        }
        if self.method is not None:
            out["method"] = self.method
        if self.correlation_id is not None:
            out["correlation_id"] = self.correlation_id
        if self.stream_id is not None:
            out["stream_id"] = self.stream_id
        return out

    # -- удобные конструкторы ------------------------------------------------

    @staticmethod
    def request(method: str, payload: dict[str, Any], *, id: str,
                trace_id: str | None = None, v: int = PROTOCOL_VERSION,
                stream_id: int | None = None) -> "Envelope":
        return Envelope(type=MessageType.REQUEST, id=id, method=method,
                        payload=payload, trace_id=trace_id or require_trace(),
                        v=v, stream_id=stream_id, timestamp=time.time())

    @staticmethod
    def event(method: str, payload: dict[str, Any], *, id: str,
              trace_id: str | None = None, v: int = PROTOCOL_VERSION,
              stream_id: int | None = None) -> "Envelope":
        """
        Событие.

        `trace_id` по умолчанию берётся из контекста обработки (`4.0-D15`), а
        не задаётся вызывающим: событие рождается глубоко — реестр вызывает
        исполнение, исполнение поднимает событие, — и требовать, чтобы каждый
        участник цепочки протащил идентификатор, значит однажды его потерять.
        """
        return Envelope(type=MessageType.EVENT, id=id, method=method,
                        payload=payload, trace_id=trace_id or require_trace(),
                        v=v, stream_id=stream_id, timestamp=time.time())

    def reply(self, payload: dict[str, Any], *, id: str) -> "Envelope":
        """
        Ответ на этот запрос.

        `trace_id` и версия наследуются, а не задаются заново: трассировка
        сквозная по определению (§14), и восстанавливать её вручную на каждом
        ответе значит однажды забыть.
        """
        return Envelope(type=MessageType.RESPONSE, id=id,
                        correlation_id=self.id, payload=payload,
                        trace_id=self.trace_id, v=self.v,
                        stream_id=self.stream_id, timestamp=time.time())

    def fail(self, error, *, id: str) -> "Envelope":
        """Ошибка в ответ на этот запрос. `error` — `ProtocolError`."""
        return Envelope(type=MessageType.ERROR, id=id,
                        correlation_id=self.id, payload=error.to_payload(),
                        trace_id=self.trace_id, v=self.v,
                        stream_id=self.stream_id, timestamp=time.time())


def _validate(type_, id_, v, timestamp, trace_id, method, correlation_id,
              stream_id, payload):
    def bad(text, **details):
        raise fault(ERROR_INVALID_ENVELOPE, text, **details)

    if type_ not in ALL_TYPES:
        bad(f"неизвестный тип сообщения: {type_!r}", field="type")
    # bool — подкласс int, и «истина» вместо номера версии прошла бы молча.
    if isinstance(v, bool) or not isinstance(v, int) or v < 1:
        bad("версия протокола должна быть целым числом от 1", field="v")
    if not isinstance(id_, str) or not id_:
        bad("идентификатор сообщения обязателен", field="id")
    if isinstance(timestamp, bool) or not isinstance(timestamp, (int, float)):
        bad("время отправки обязательно", field="timestamp")
    if not isinstance(trace_id, str) or not trace_id:
        bad("trace_id обязателен на каждом сообщении", field="trace_id")
    if not isinstance(payload, dict):
        bad("payload обязан быть объектом; пустой объект, если нечего сказать",
            field="payload")
    if stream_id is not None and (isinstance(stream_id, bool)
                                  or not isinstance(stream_id, int)):
        bad("stream_id обязан быть числом", field="stream_id")

    present = {"method": method, "correlation_id": correlation_id}
    for name in _EXTRA_REQUIRED[type_]:
        value = present[name]
        if not isinstance(value, str) or not value:
            bad(f"для сообщения типа {type_!r} обязательно поле {name!r}",
                field=name)


def encode(envelope: Envelope) -> bytes:
    """Конверт → байты JSON в UTF-8, без кадрового префикса."""
    return json.dumps(envelope.to_dict(), ensure_ascii=False,
                      separators=(",", ":")).encode("utf-8")


def decode(raw: bytes) -> Envelope:
    """
    Байты JSON → конверт.

    Незнакомые поля отбрасываются молча — см. заголовок модуля.
    """
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise fault(ERROR_INVALID_ENVELOPE,
                    "сообщение не разбирается как JSON в UTF-8",
                    reason=str(exc)) from None
    if not isinstance(data, dict):
        raise fault(ERROR_INVALID_ENVELOPE,
                    "сообщение обязано быть объектом")

    missing = [name for name in ("v", "type", "id", "timestamp", "trace_id",
                                 "payload") if name not in data]
    if missing:
        raise fault(ERROR_INVALID_ENVELOPE,
                    "в конверте нет обязательных полей",
                    fields=missing)

    return Envelope(
        type=data["type"],
        id=data["id"],
        timestamp=data["timestamp"],
        trace_id=data["trace_id"],
        payload=data["payload"],
        v=data["v"],
        method=data.get("method"),
        correlation_id=data.get("correlation_id"),
        stream_id=data.get("stream_id"),
    )


def encode_frame(envelope: Envelope) -> bytes:
    """Кадр управляющего канала: длина полезной нагрузки, затем она сама."""
    body = encode(envelope)
    if len(body) > CONTROL_FRAME_LIMIT:
        raise fault(
            ERROR_FRAME_TOO_LARGE,
            "сообщение больше предела управляющего канала",
            size=len(body), limit=CONTROL_FRAME_LIMIT)
    return _HEADER.pack(len(body)) + body


class FrameDecoder:
    """
    Сборка кадров из потока байтов.

    Канал отдаёт байты как придётся: половину заголовка сейчас, полтора кадра
    потом. Декодер держит остаток между вызовами и отдаёт готовые сообщения.

    **Предел проверяется по заявленной длине, до выделения памяти.** Иначе
    предел не защищает ни от чего: сторона, объявившая кадр в четыре гигабайта,
    добьётся своего ровно тем, что мы честно дождёмся его целиком.
    """

    def __init__(self, limit: int = CONTROL_FRAME_LIMIT):
        self._limit = limit
        self._buffer = bytearray()

    def feed(self, chunk: bytes) -> Iterator[Envelope]:
        """Принять кусок потока и отдать все сообщения, ставшие целыми."""
        self._buffer.extend(chunk)
        while True:
            if len(self._buffer) < _HEADER.size:
                return
            (size,) = _HEADER.unpack_from(self._buffer, 0)
            if size > self._limit:
                # Буфер не очищается: после такого канал разрывают, а не
                # пытаются продолжить с середины неизвестно чего.
                raise fault(
                    ERROR_FRAME_TOO_LARGE,
                    "объявленный размер кадра больше предела",
                    size=size, limit=self._limit)
            if len(self._buffer) < _HEADER.size + size:
                return
            body = bytes(self._buffer[_HEADER.size:_HEADER.size + size])
            del self._buffer[:_HEADER.size + size]
            yield decode(body)

    @property
    def pending(self) -> int:
        """Сколько байт лежит недособранными — для отладки и тестов."""
        return len(self._buffer)


class IdGenerator:
    """
    Идентификаторы сообщений, уникальные в пределах сессии.

    Префикс называет сторону (`s-` оболочка, `c-` ядро), чтобы в общем журнале
    двух процессов было видно, кто отправитель, без обращения к содержимому.
    Счётчик, а не случайность: в отладке важно, что номера идут подряд —
    пропуск виден глазом.
    """

    def __init__(self, prefix: str):
        if not prefix:
            raise ValueError("префикс идентификатора обязателен")
        self._prefix = prefix
        self._n = 0

    def next(self) -> str:
        self._n += 1
        return f"{self._prefix}{self._n:04d}"
