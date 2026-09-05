"""
Events: the core reports without being asked.

Plan items `4.0-D11` (push events) and `4.0-D06` (streamed text);
specification, §7 and §10.

**An event guarantees nothing about delivery.** If the shell restarts, the
event is lost — and that is a property, not a defect. What must not be lost
lies in the store and is requested after reconnecting; an event only reports
that it is worth looking there right now.

**An unknown event is ignored by the receiver in silence** (§3). The
asymmetry with a request is deliberate: a missed request is a lost action, a
missed event is a lost notification. Thanks to this the core can introduce a
new event without breaking an old shell — and the compatibility rule "an
event may be added without changing the version" stops being a promise in
words only.

**The payload is checked at the sender, not at the receiver.** An event with
wrong fields is a defect of the sending side, and it is better to learn of
it at home. At the receiver, a broken event drops precisely itself: breaking
off the channel because of one spoiled notification is worse than losing it.

The catalogue is checked against two sources at once
(`tools/test_wire.py`): the list in `core/protocol.py`, which the
specification was written from, and the table in §6 of the specification
itself. Three lists that nobody compares drift apart.
"""

from dataclasses import dataclass, field
from typing import Any, Callable

from core.wire.envelope import Envelope
from core.wire.errors import (ERROR_INVALID_PAYLOAD, ERROR_INVALID_STATE,
                              fault)

#: The types of fields. The same dictionary as the tool registry's,
#: deliberately: two different languages for describing data inside one core
#: would have to be reconciled.
_TYPES = {
    "string": str,
    "boolean": bool,
    "integer": int,
    "number": (int, float),
    "object": dict,
    "array": list,
    # A task's result is anything at all: a string for rewritten text, an
    # object for a parse, a list for a search. Imposing a shape here would
    # mean deciding for version five what long tasks do.
    "any": object,
}


@dataclass(frozen=True)
class Field:
    name: str
    type: str
    choices: tuple[str, ...] = ()
    required: bool = True
    low: float | None = None
    high: float | None = None


@dataclass(frozen=True)
class EventSpec:
    name: str
    fields: tuple[Field, ...] = ()
    note: str = ""


def _e(name, *fields, note=""):
    return EventSpec(name, tuple(fields), note)


def _f(name, type_, *choices, required=True, low=None, high=None):
    return Field(name, type_, tuple(choices), required, low, high)


#: All the events. The first twelve are 3.1.0 behaviour carried over
#: unchanged; the rest appear together with the protocol.
EVENTS: dict[str, EventSpec] = {s.name: s for s in (
    # --- the microphone -----------------------------------------------------
    _e("listening.started", note="началось однократное прослушивание"),
    _e("listening.stopped", note="прослушивание закончилось"),
    _e("listening.capturing", _f("active", "boolean"),
       note="идёт захват звука"),
    _e("listening.always", _f("enabled", "boolean"),
       note="режим постоянного прослушивания"),
    _e("speech.recognized", _f("text", "string"), note="распознанная фраза"),

    # --- the assistant's answers --------------------------------------------
    _e("assistant.response", _f("text", "string")),
    _e("assistant.error", _f("text", "string")),
    _e("assistant.thinking", _f("active", "boolean"),
       note="модель думает; это может занять секунды, и молчать нельзя"),

    # --- data ---------------------------------------------------------------
    _e("history.changed", note="содержимое диалога изменилось"),
    _e("reminder.fired", _f("item", "object"),
       note="первый настоящий потребитель канала событий (4.0-E05)"),

    # --- requests to the shell, expressed as an event -----------------------
    _e("apps.not_found", _f("query", "string")),
    _e("window.action",
       _f("action", "string", "screenshot", "minimize", "show", "quit"),
       note="ядро сообщает о намерении, оболочка решает, как это выглядит"),

    # --- streamed text (4.0-D06, §7) ----------------------------------------
    _e("stream.chunk", _f("text", "string"),
       note="часть ответа; поток назван stream_id в конверте"),
    _e("stream.end", _f("reason", "string", "done", "cancelled", "failed"),
       note="при failed рядом идёт error с тем же stream_id"),

    # --- long tasks (4.0-D09, §9) -------------------------------------------
    _e("task.progress", _f("task_id", "string"), _f("note", "string"),
       _f("fraction", "number", required=False, low=0.0, high=1.0),
       note="доля необязательна: она известна не всякой задаче, "
            "а пояснение обязано быть — молчаливый прогресс бесполезен"),
    _e("task.partial", _f("task_id", "string"), _f("result", "any"),
       note="промежуточный результат; сколько угодно раз"),
    _e("task.done", _f("task_id", "string"), _f("result", "any")),
    _e("task.failed", _f("task_id", "string"), _f("error", "object")),
    _e("task.cancelled", _f("task_id", "string")),
)}

ALL_EVENTS = tuple(EVENTS)


def validate_event(name: str, payload: dict[str, Any]) -> None:
    """
    Check an event's payload before sending.

    A surplus field is an error, as in the tool registry: here both sides
    are described by one document, and a surplus field means the sender
    believed it was reporting one thing and is reporting another. The
    concession in §4 about unfamiliar fields applies to the envelope, not to
    the payload: the envelope is common to every message and grows with
    protocol versions, whereas the payload belongs to a particular event and
    grows together with it.
    """
    spec = EVENTS.get(name)
    if spec is None:
        raise fault(ERROR_INVALID_PAYLOAD,
                    f"событие {name!r} не объявлено в каталоге", event=name)
    if not isinstance(payload, dict):
        raise fault(ERROR_INVALID_PAYLOAD, "нагрузка обязана быть объектом",
                    event=name)

    expected = {f.name: f for f in spec.fields}
    extra = sorted(set(payload) - set(expected))
    if extra:
        raise fault(ERROR_INVALID_PAYLOAD,
                    f"у события {name!r} нет таких полей",
                    event=name, fields=extra)
    for fname, spec_field in expected.items():
        if fname not in payload:
            if not spec_field.required:
                continue
            raise fault(ERROR_INVALID_PAYLOAD,
                        f"у события {name!r} не хватает поля {fname!r}",
                        event=name, field=fname)
        value = payload[fname]
        wanted = _TYPES[spec_field.type]
        # bool is a subclass of int: "true" instead of a number would pass in silence.
        if spec_field.type in ("integer", "number") and isinstance(value, bool):
            raise fault(ERROR_INVALID_PAYLOAD,
                        f"поле {fname!r} обязано быть числом, а не логическим",
                        event=name, field=fname)
        if not isinstance(value, wanted):
            raise fault(ERROR_INVALID_PAYLOAD,
                        f"поле {fname!r} обязано быть {spec_field.type}",
                        event=name, field=fname, got=type(value).__name__)
        if spec_field.choices and value not in spec_field.choices:
            raise fault(ERROR_INVALID_PAYLOAD,
                        f"поле {fname!r} принимает только "
                        f"{', '.join(spec_field.choices)}",
                        event=name, field=fname, got=value)
        if spec_field.low is not None and value < spec_field.low:
            raise fault(ERROR_INVALID_PAYLOAD,
                        f"поле {fname!r} меньше {spec_field.low}",
                        event=name, field=fname, got=value)
        if spec_field.high is not None and value > spec_field.high:
            raise fault(ERROR_INVALID_PAYLOAD,
                        f"поле {fname!r} больше {spec_field.high}",
                        event=name, field=fname, got=value)


def event(name: str, payload: dict[str, Any] | None = None, *, id: str,
          stream_id: int | None = None, trace_id: str | None = None,
          v: int = 1) -> Envelope:
    """Build an event, checking the payload. `trace_id` comes from the context (D15)."""
    payload = dict(payload or {})
    validate_event(name, payload)
    return Envelope.event(name, payload, id=id, stream_id=stream_id,
                          trace_id=trace_id, v=v)


class Router:
    """
    Receiving events on the receiver's side.

    An unfamiliar event is not an error: `dispatch` returns `False` and says
    nothing. A familiar but spoiled one drops only itself — the handler is
    not called, and the reason goes to the observer if one is appointed.
    """

    def __init__(self, on_broken: Callable[[str, Exception], None] | None = None):
        self._handlers: dict[str, list[Callable]] = {}
        self._on_broken = on_broken
        self.ignored: list[str] = []

    def on(self, name: str, handler: Callable[[dict], Any]):
        if name not in EVENTS:
            raise ValueError(
                f"подписка на необъявленное событие {name!r}: "
                "события заводятся в каталоге, а не по месту подписки")
        self._handlers.setdefault(name, []).append(handler)
        return handler

    def dispatch(self, envelope: Envelope) -> bool:
        """`True` — the event was delivered to at least one subscriber."""
        name = envelope.method or ""
        if name not in EVENTS:
            self.ignored.append(name)
            return False
        try:
            validate_event(name, envelope.payload)
        except Exception as exc:
            if self._on_broken is not None:
                self._on_broken(name, exc)
            return False
        handlers = list(self._handlers.get(name, ()))
        for handler in handlers:
            handler(envelope.payload)
        return bool(handlers)


# ---------------------------------------------------------------------------
# Streamed text (4.0-D06, §7)
# ---------------------------------------------------------------------------
#: How a stream may end.
STREAM_DONE = "done"
STREAM_CANCELLED = "cancelled"
STREAM_FAILED = "failed"


class StreamSender:
    """
    The sender of a stream of text.

    A model's answer goes in parts, so that speech can begin before the
    answer is finished. In 4.0 there is no consumer yet — it appears in 5.0;
    it is laid down now, because adding it later costs a rewrite of both
    sides.
    """

    def __init__(self, ids, first_stream_id: int = 1):
        self._ids = ids
        self._next = first_stream_id
        self.open: set[int] = set()

    def begin(self) -> int:
        """Take a stream number. It also goes into the answer that opens the stream."""
        stream_id = self._next
        self._next += 1
        self.open.add(stream_id)
        return stream_id

    def chunk(self, stream_id: int, text: str) -> Envelope:
        self._require(stream_id)
        return event("stream.chunk", {"text": text},
                     id=self._ids.next(), stream_id=stream_id)

    def end(self, stream_id: int, reason: str = STREAM_DONE) -> Envelope:
        self._require(stream_id)
        message = event("stream.end", {"reason": reason},
                        id=self._ids.next(), stream_id=stream_id)
        self.open.discard(stream_id)
        return message

    def close_all(self) -> int:
        """Forget every stream: a disconnection takes them with it (§13)."""
        count = len(self.open)
        self.open.clear()
        return count

    def _require(self, stream_id: int):
        if stream_id not in self.open:
            raise fault(ERROR_INVALID_STATE,
                        f"поток {stream_id} не открыт или уже закрыт",
                        stream_id=stream_id)


class StreamReceiver:
    """
    Assembling a stream on the receiver's side.

    **A part of a stream may arrive before the answer that opened the
    stream** — messages are asynchronous, and §7 expressly requires this. So
    the receiver accumulates by stream number and does not ask whether it
    knows about it: a receiver that discards early parts loses the beginning
    of every fast answer, and the more often the faster the model answers.
    """

    def __init__(self):
        self._parts: dict[int, list[str]] = {}
        self.finished: dict[int, str] = {}

    def accept(self, envelope: Envelope) -> bool:
        """Accept `stream.chunk` or `stream.end`. `False` — not about a stream."""
        name = envelope.method
        stream_id = envelope.stream_id
        if stream_id is None or name not in ("stream.chunk", "stream.end"):
            return False
        validate_event(name, envelope.payload)
        if name == "stream.chunk":
            self._parts.setdefault(stream_id, []).append(
                envelope.payload["text"])
        else:
            self.finished[stream_id] = envelope.payload["reason"]
        return True

    def text(self, stream_id: int) -> str:
        return "".join(self._parts.get(stream_id, ()))

    def done(self, stream_id: int) -> bool:
        return stream_id in self.finished
