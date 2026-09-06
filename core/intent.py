"""
The data model: intent, action, result.

Plan item 4.0-B01. At the moment strings and dicts travel through the code:
the pipeline guesses the intent and performs it on the spot, so "what the
user wanted" is nowhere expressed separately from "what we did". While these
are one and the same, the parse cannot be checked without side effects, the
decision cannot be sent over the protocol, and a language model cannot be
placed alongside the rules.

Three types separate what is now fused:

    Intent  — what the user wanted. Pure data, no actions.
    Action  — what has to be done. Data too: a description, not a call.
    Result  — what came of it.

All three serialise to JSON without loss: they travel over the protocol (see
docs/protocol/PROTOCOL-v1.md), and any field that cannot be written to JSON
is inadmissible here.

There is deliberately no Qt here: the module lies in the core.
"""

import json
from dataclasses import dataclass, field, replace
from types import MappingProxyType


# ---------------------------------------------------------------------------
# The catalogue of intents
# ---------------------------------------------------------------------------
# The names are not invented afresh: they are derived from 3.1.0's actual
# behaviour (docs/INVENTORY-3.1.0.md) and are already used by the golden
# suite. They must not be changed without amending that suite — 112 cases
# there refer to these strings.
INTENTS = {
    # launching programs
    "app.launch":         "Запустить программу. Аргументы: app",
    "app.ambiguous":      "Несколько кандидатов, нужен выбор. Аргументы: options, query",
    "app.not_found":      "Программа не найдена. Аргументы: query",
    "app.launch_failed":  "Программа найдена, но не запустилась. Аргументы: app",

    # reminders
    "reminder.create":    "Создать напоминание. Аргументы: kind, seconds или at, text",
    "reminder.list":      "Показать запланированное. Аргументы: empty",
    "reminder.cancel":    "Отменить запланированное. Аргументы: empty, count",

    # the system
    "system.action":      "Выполнить системное действие. Аргументы: action",
    "system.confirm":     "Опасное действие, нужно подтверждение. Аргументы: action",
    "command.confirm":    "Пользовательская команда опасна, нужно подтверждение",

    # answers
    "calc":               "Арифметика. Аргументы: result",
    "calc.zero_division": "Деление на ноль",
    "websearch":          "Явный поиск в интернете. Аргументы: query",
    "builtin.answer":     "Встроенный ответ. Аргументы: topic",

    # the dialogue
    "ask.wake":           "Прозвучало слово активации без команды",
    "cancelled":          "Пользователь отказался от предложенного",
    "silence":            "Ничего не делаем и молчим",

    # the pipeline's tail
    "llm.answer":         "Ответила языковая модель. Аргументы: text",
    "fallback.search":    "Не разобрали — ищем в интернете. Аргументы: query",
    "fallback.none":      "Не разобрали и не ищем",

    # internal
    "plugin":             "Фразу забрал плагин. Аргументы: plugin_id",
    "user_command":       "Сработала пользовательская команда. Аргументы: command_id",
    "unknown":            "Классифицировать не удалось — дефект разбора или прогонщика",
}

#: Intents after which the core waits for the user's answer.
PENDING_INTENTS = frozenset({"app.ambiguous", "system.confirm",
                             "command.confirm"})


def _frozen(mapping):
    """
    A dict that cannot be changed.

    `frozen=True` on a dataclass forbids reassigning fields but does not
    prevent changing a dict inside a field. Without this an "immutable"
    Intent could be spoiled in silence along the way — exactly what it was
    introduced to prevent.
    """
    return MappingProxyType(dict(mapping or {}))


class UnknownIntent(ValueError):
    """The intent's name is not in the catalogue."""


def check_intent_name(name):
    """A checked name, or UnknownIntent.

    A typo in an intent's name would otherwise pass in silence and turn into
    a divergence that has to be hunted for by eye.
    """
    if name not in INTENTS:
        raise UnknownIntent(f"неизвестное намерение: {name!r}")
    return name


# ---------------------------------------------------------------------------
# The types
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Intent:
    """
    What the user wanted.

    Immutable: an intent is the parse's conclusion, and rewriting it along
    the way means losing what was decided. A changed copy comes from
    `with_`.
    """

    name: str
    args: dict = field(default_factory=dict)
    # How confident the parse is. The rules give 1.0; the language model
    # step (4.0-B02) will give less, and that number can be used to decide
    # whether to ask again.
    confidence: float = 1.0
    # Which pipeline step produced the intent — for the journal and for debugging.
    stage: str = ""
    # The original phrase. Needed to explain the decision (4.0b-B04, "Why?").
    text: str = ""

    def __post_init__(self):
        check_intent_name(self.name)
        object.__setattr__(self, "args", _frozen(self.args))

    @property
    def needs_answer(self):
        """Whether the core waits for the user's answer after this intent."""
        return self.name in PENDING_INTENTS

    def arg(self, key, default=None):
        return self.args.get(key, default)

    def with_(self, **changes):
        """A copy with changed fields."""
        return replace(self, **changes)

    def to_dict(self):
        return {"name": self.name, "args": dict(self.args),
                "confidence": self.confidence, "stage": self.stage,
                "text": self.text}

    @classmethod
    def from_dict(cls, data):
        return cls(name=data["name"], args=dict(data.get("args") or {}),
                   confidence=float(data.get("confidence", 1.0)),
                   stage=str(data.get("stage", "")),
                   text=str(data.get("text", "")))

    def __str__(self):
        args = " ".join(f"{k}={v!r}" for k, v in sorted(self.args.items()))
        return f"{self.name}({args})" if args else f"{self.name}()"


@dataclass(frozen=True)
class Action:
    """
    What has to be done. A description, not a call.

    Separated from Intent, because one intent can give different actions:
    "shut down the computer" is either a question or a shutdown, depending
    on whether it was confirmed. And because an action can be shown before
    it is performed — that is the basis of previewing dangerous operations
    (4.0-C05).
    """

    kind: str
    args: dict = field(default_factory=dict)
    #: Whether a valid confirmation_id is needed (see the protocol, §11).
    confirm_required: bool = False
    #: The permissions the action requires (4.0-C04).
    permissions: tuple = ()

    def __post_init__(self):
        object.__setattr__(self, "args", _frozen(self.args))
        object.__setattr__(self, "permissions", tuple(self.permissions))

    def to_dict(self):
        return {"kind": self.kind, "args": dict(self.args),
                "confirm_required": self.confirm_required,
                "permissions": list(self.permissions)}

    @classmethod
    def from_dict(cls, data):
        return cls(kind=data["kind"], args=dict(data.get("args") or {}),
                   confirm_required=bool(data.get("confirm_required")),
                   permissions=tuple(data.get("permissions") or ()))


@dataclass(frozen=True)
class Result:
    """
    What came of it.

    `response` is what Rina will say; `error_code` is what the logic
    branches on. Separated for the same reason as in the protocol's error
    catalogue: the text is translated, the code is not.
    """

    ok: bool
    response: str = ""
    error_code: str = ""
    data: dict = field(default_factory=dict)

    def __post_init__(self):
        object.__setattr__(self, "data", _frozen(self.data))

    @classmethod
    def success(cls, response="", **data):
        return cls(ok=True, response=response, data=data)

    @classmethod
    def failure(cls, response="", error_code="internal", **data):
        return cls(ok=False, response=response, error_code=error_code,
                   data=data)

    def with_data(self, **extra):
        """A copy with data added: Result is immutable."""
        merged = dict(self.data)
        merged.update(extra)
        return Result(ok=self.ok, response=self.response,
                      error_code=self.error_code, data=merged)

    def to_dict(self):
        return {"ok": self.ok, "response": self.response,
                "error_code": self.error_code, "data": dict(self.data)}

    @classmethod
    def from_dict(cls, data):
        return cls(ok=bool(data.get("ok")),
                   response=str(data.get("response", "")),
                   error_code=str(data.get("error_code", "")),
                   data=dict(data.get("data") or {}))


# ---------------------------------------------------------------------------
def assert_json_safe(obj):
    """
    Checks that an object will survive the journey over the protocol.

    The protocol's rule: everything is serialisable, no exceptions. A type
    that cannot be written to JSON will be discovered here rather than at
    the first run of the two processes.
    """
    json.dumps(obj.to_dict(), ensure_ascii=False)
    return True
