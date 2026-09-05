"""
The message envelope and control-channel framing.

Plan item `4.0-D04`; specification, §2 and §3.

In 3.1.0 there was no envelope at all: an event carried only its payload,
and there was nothing to tie a click in the window to what happened in the
core — because everything happened in one process and there was nothing to
tie. Across two processes that stops working, and the envelope is the price
paid for the split.

**The envelope's fields are present in every message without exception.**
The words "without exception" are not rhetoric here: an envelope that is
sometimes incomplete demands a check on each side at every receiver, and one
of those checks will one day be forgotten.

**Unknown envelope fields are skipped in silence.** This is the exact
opposite of the tool registry's rule, where a surplus argument is an error
(`core/tools.py`), and the difference is not one of tidiness but of who is
talking to whom. Inside one process the caller and the callee are built
together: a surplus argument means somebody made a mistake just now. Across
a version boundary the sides are built separately, and the compatibility
rules (§4) expressly allow adding an optional field without changing the
protocol version. A receiver that trips over an unfamiliar field turns that
permission into a lie and makes staged upgrades impossible.
"""

import json
import struct
import time
from dataclasses import dataclass, field
from typing import Any, Iterator

from core.wire.errors import (ERROR_FRAME_TOO_LARGE, ERROR_INVALID_ENVELOPE,
                              fault)
from core.trace import new_trace_id, require_trace

#: The limit of one control message (§2). More than that is either a defect
#: or an attempt to exhaust memory, and both are cured by disconnecting
#: rather than by parsing.
CONTROL_FRAME_LIMIT = 1024 * 1024

#: The length of a frame prefix: 4 bytes, big-endian, unsigned.
_HEADER = struct.Struct(">I")

PROTOCOL_VERSION = 1


class MessageType:
    REQUEST = "request"
    RESPONSE = "response"
    EVENT = "event"
    ERROR = "error"


ALL_TYPES = (MessageType.REQUEST, MessageType.RESPONSE,
             MessageType.EVENT, MessageType.ERROR)

#: Which fields are required beyond the common ones, depending on the message
#: type (§3). A request and an event must name the method; a response and an
#: error must say what they are answering. A response without a
#: `correlation_id` is indistinguishable from an event and therefore useless.
_EXTRA_REQUIRED = {
    MessageType.REQUEST: ("method",),
    MessageType.EVENT: ("method",),
    MessageType.RESPONSE: ("correlation_id",),
    MessageType.ERROR: ("correlation_id",),
}


@dataclass(frozen=True)
class Envelope:
    """
    One message of the control channel.

    Frozen: a message that has been through the journal and the trace must
    not differ from what went into the channel.
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
        """A dict for serialisation: optional fields are omitted."""
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

    # -- convenience constructors ---------------------------------------------

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
        An event.

        `trace_id` is taken from the handling context by default
        (`4.0-D15`) rather than set by the caller: an event is born deep
        down — the registry calls the execution, the execution raises the
        event — and requiring every link in the chain to carry the
        identifier through means losing it one day.
        """
        return Envelope(type=MessageType.EVENT, id=id, method=method,
                        payload=payload, trace_id=trace_id or require_trace(),
                        v=v, stream_id=stream_id, timestamp=time.time())

    def reply(self, payload: dict[str, Any], *, id: str) -> "Envelope":
        """
        A response to this request.

        `trace_id` and the version are inherited rather than set afresh: a
        trace is end-to-end by definition (§14), and restoring it by hand on
        every response means forgetting it one day.
        """
        return Envelope(type=MessageType.RESPONSE, id=id,
                        correlation_id=self.id, payload=payload,
                        trace_id=self.trace_id, v=self.v,
                        stream_id=self.stream_id, timestamp=time.time())

    def fail(self, error, *, id: str) -> "Envelope":
        """An error in answer to this request. `error` is a `ProtocolError`."""
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
    # bool is a subclass of int, and "true" instead of a version number would pass in silence.
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
    """An envelope to JSON bytes in UTF-8, without the frame prefix."""
    return json.dumps(envelope.to_dict(), ensure_ascii=False,
                      separators=(",", ":")).encode("utf-8")


def decode(raw: bytes) -> Envelope:
    """
    JSON bytes to an envelope.

    Unfamiliar fields are discarded in silence — see the module header.
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
    """A control-channel frame: the payload's length, then the payload."""
    body = encode(envelope)
    if len(body) > CONTROL_FRAME_LIMIT:
        raise fault(
            ERROR_FRAME_TOO_LARGE,
            "сообщение больше предела управляющего канала",
            size=len(body), limit=CONTROL_FRAME_LIMIT)
    return _HEADER.pack(len(body)) + body


class FrameDecoder:
    """
    Assembling frames out of a stream of bytes.

    A channel gives out bytes as it pleases: half a header now, a frame and
    a half later. The decoder keeps the remainder between calls and hands
    back whatever messages have become whole.

    **The limit is checked against the declared length, before memory is
    allocated.** Otherwise the limit protects against nothing: a side that
    announced a four-gigabyte frame gets its way precisely because we shall
    honestly wait for the whole of it.
    """

    def __init__(self, limit: int = CONTROL_FRAME_LIMIT):
        self._limit = limit
        self._buffer = bytearray()

    def feed(self, chunk: bytes) -> Iterator[Envelope]:
        """Take a piece of the stream and hand back every message now whole."""
        self._buffer.extend(chunk)
        while True:
            if len(self._buffer) < _HEADER.size:
                return
            (size,) = _HEADER.unpack_from(self._buffer, 0)
            if size > self._limit:
                # The buffer is not cleared: after such a thing the channel
                # is broken off rather than continued from the middle of who
                # knows what.
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
        """How many bytes lie unassembled — for debugging and tests."""
        return len(self._buffer)


class IdGenerator:
    """
    Message identifiers, unique within a session.

    The prefix names the side (`s-` the shell, `c-` the core), so that in a
    shared journal of two processes it is visible who the sender is without
    looking at the content. A counter rather than randomness: in debugging
    it matters that the numbers run consecutively — a gap is visible to the
    eye.
    """

    def __init__(self, prefix: str):
        if not prefix:
            raise ValueError("префикс идентификатора обязателен")
        self._prefix = prefix
        self._n = 0

    def next(self) -> str:
        self._n += 1
        return f"{self._prefix}{self._n:04d}"
