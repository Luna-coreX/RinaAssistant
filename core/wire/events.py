"""
События: ядро сообщает, не спрашивая.

Задачи плана `4.0-D11` (push-события) и `4.0-D06` (потоковый текст);
спецификация, §7 и §10.

**Событие ничего не гарантирует о доставке.** Если оболочка перезапускается,
событие теряется — и это не дефект, а свойство. То, что терять нельзя, лежит в
хранилище и запрашивается после переподключения; событие лишь сообщает, что
смотреть туда стоит прямо сейчас.

**Неизвестное событие получатель игнорирует молча** (§3). Асимметрия с
запросом намеренна: пропущенный запрос — потерянное действие, пропущенное
событие — потерянное уведомление. Благодаря этому ядро может завести новое
событие, не ломая старую оболочку, — и правило совместимости «добавить событие
можно, не меняя версию» перестаёт быть обещанием на словах.

**Полезная нагрузка проверяется у отправителя, а не у получателя.** Событие с
неверными полями — дефект отправляющей стороны, и узнать о нём лучше дома.
У получателя же сломанное событие роняет ровно себя: обрывать канал из-за
одного испорченного уведомления хуже, чем его потерять.

Каталог сверяется с двумя источниками сразу (`tools/test_wire.py`): с
перечнем `core/protocol.py`, по которому писалась спецификация, и с таблицей
§6 самой спецификации. Три списка, которые никто не сверяет, разъезжаются.
"""

from dataclasses import dataclass, field
from typing import Any, Callable

from core.wire.envelope import Envelope
from core.wire.errors import ERROR_INVALID_PAYLOAD, fault

#: Типы полей. Тот же словарь, что у реестра инструментов, — намеренно:
#: два разных языка описания данных внутри одного ядра пришлось бы сверять.
_TYPES = {
    "string": str,
    "boolean": bool,
    "integer": int,
    "number": (int, float),
    "object": dict,
    "array": list,
}


@dataclass(frozen=True)
class Field:
    name: str
    type: str
    choices: tuple[str, ...] = ()


@dataclass(frozen=True)
class EventSpec:
    name: str
    fields: tuple[Field, ...] = ()
    note: str = ""


def _e(name, *fields, note=""):
    return EventSpec(name, tuple(fields), note)


def _f(name, type_, *choices):
    return Field(name, type_, tuple(choices))


#: Все события. Первые двенадцать — поведение 3.1.0, перенесённое без
#: изменений; остальные появляются вместе с протоколом.
EVENTS: dict[str, EventSpec] = {s.name: s for s in (
    # --- микрофон -----------------------------------------------------------
    _e("listening.started", note="началось однократное прослушивание"),
    _e("listening.stopped", note="прослушивание закончилось"),
    _e("listening.capturing", _f("active", "boolean"),
       note="идёт захват звука"),
    _e("listening.always", _f("enabled", "boolean"),
       note="режим постоянного прослушивания"),
    _e("speech.recognized", _f("text", "string"), note="распознанная фраза"),

    # --- ответы ассистента --------------------------------------------------
    _e("assistant.response", _f("text", "string")),
    _e("assistant.error", _f("text", "string")),
    _e("assistant.thinking", _f("active", "boolean"),
       note="модель думает; это может занять секунды, и молчать нельзя"),

    # --- данные -------------------------------------------------------------
    _e("history.changed", note="содержимое диалога изменилось"),
    _e("reminder.fired", _f("item", "object"),
       note="первый настоящий потребитель канала событий (4.0-E05)"),

    # --- запросы к оболочке, выраженные событием ----------------------------
    _e("apps.not_found", _f("query", "string")),
    _e("window.action",
       _f("action", "string", "screenshot", "minimize", "show", "quit"),
       note="ядро сообщает о намерении, оболочка решает, как это выглядит"),

    # --- потоковый текст (4.0-D06, §7) --------------------------------------
    _e("stream.chunk", _f("text", "string"),
       note="часть ответа; поток назван stream_id в конверте"),
    _e("stream.end", _f("reason", "string", "done", "cancelled", "failed"),
       note="при failed рядом идёт error с тем же stream_id"),
)}

ALL_EVENTS = tuple(EVENTS)


def validate_event(name: str, payload: dict[str, Any]) -> None:
    """
    Проверить нагрузку события перед отправкой.

    Лишнее поле — ошибка, как и в реестре инструментов: здесь обе стороны
    описаны одним документом, и лишнее поле значит, что отправитель считал,
    будто сообщает одно, а сообщает другое. Послабление §4 про незнакомые
    поля относится к конверту, а не к нагрузке: конверт общий для всех
    сообщений и растёт версиями протокола, нагрузка же принадлежит
    конкретному событию и растёт вместе с ним.
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
            raise fault(ERROR_INVALID_PAYLOAD,
                        f"у события {name!r} не хватает поля {fname!r}",
                        event=name, field=fname)
        value = payload[fname]
        wanted = _TYPES[spec_field.type]
        # bool — подкласс int: «истина» вместо числа прошла бы молча.
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


def event(name: str, payload: dict[str, Any] | None = None, *, id: str,
          stream_id: int | None = None, trace_id: str | None = None,
          v: int = 1) -> Envelope:
    """Собрать событие, проверив нагрузку. `trace_id` — из контекста (D15)."""
    payload = dict(payload or {})
    validate_event(name, payload)
    return Envelope.event(name, payload, id=id, stream_id=stream_id,
                          trace_id=trace_id, v=v)


class Router:
    """
    Приём событий на стороне получателя.

    Незнакомое событие не ошибка: `dispatch` возвращает `False` и молчит.
    Знакомое, но испорченное, роняет только себя — обработчик не вызывается,
    а причина уходит наблюдателю, если он назначен.
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
        """`True` — событие доставлено хотя бы одному подписчику."""
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
# Потоковый текст (4.0-D06, §7)
# ---------------------------------------------------------------------------
#: Чем поток может закончиться.
STREAM_DONE = "done"
STREAM_CANCELLED = "cancelled"
STREAM_FAILED = "failed"


class StreamSender:
    """
    Отправитель потока текста.

    Ответ модели идёт по частям, чтобы речь начиналась раньше, чем ответ
    дописан. В 4.0 потребителя ещё нет — он появляется в 5.0; заложено сейчас,
    потому что добавить потом стоит переписывания обеих сторон.
    """

    def __init__(self, ids, first_stream_id: int = 1):
        self._ids = ids
        self._next = first_stream_id
        self.open: set[int] = set()

    def begin(self) -> int:
        """Занять номер потока. Он же уходит в ответ, открывающий поток."""
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

    def _require(self, stream_id: int):
        if stream_id not in self.open:
            raise fault(ERROR_INVALID_PAYLOAD,
                        f"поток {stream_id} не открыт или уже закрыт",
                        stream_id=stream_id)


class StreamReceiver:
    """
    Сборка потока на стороне получателя.

    **Часть потока может прийти раньше ответа, открывшего поток** — сообщения
    асинхронны, и §7 прямо этого требует. Поэтому приёмник копит по номеру
    потока и не спрашивает, знает ли он о нём: приёмник, который отбрасывает
    ранние части, теряет начало каждого быстрого ответа, причём тем чаще, чем
    быстрее отвечает модель.
    """

    def __init__(self):
        self._parts: dict[int, list[str]] = {}
        self.finished: dict[int, str] = {}

    def accept(self, envelope: Envelope) -> bool:
        """Принять `stream.chunk` или `stream.end`. `False` — не про поток."""
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
