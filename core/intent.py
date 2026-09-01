"""
Модель данных: намерение, действие, результат.

Задача плана 4.0-B01. Сейчас по коду ходят строки и словари: конвейер
угадывает намерение и тут же его исполняет, поэтому «что пользователь хотел»
нигде не выражено отдельно от «что мы сделали». Пока это одно и то же, нельзя
ни проверить разбор без побочных эффектов, ни отправить решение по протоколу,
ни подставить рядом с правилами языковую модель.

Три типа разделяют то, что сейчас слито:

    Intent  — что хотел пользователь. Чистые данные, никаких действий.
    Action  — что надо сделать. Тоже данные: описание, а не вызов.
    Result  — что получилось.

Все три сериализуемы в JSON без потерь: они едут по протоколу (см.
docs/protocol/PROTOCOL-v1.md), и любое поле, которое нельзя записать в JSON,
здесь недопустимо.

Qt тут нет намеренно: модуль лежит в ядре.
"""

import json
from dataclasses import dataclass, field, replace
from types import MappingProxyType


# ---------------------------------------------------------------------------
# Каталог намерений
# ---------------------------------------------------------------------------
# Имена не придуманы заново: они выведены из фактического поведения 3.1.0
# (docs/INVENTORY-3.1.0.md) и уже используются golden-набором. Менять их
# нельзя, не поправив набор — там 112 случаев ссылаются на эти строки.
INTENTS = {
    # запуск программ
    "app.launch":         "Запустить программу. Аргументы: app",
    "app.ambiguous":      "Несколько кандидатов, нужен выбор. Аргументы: options, query",
    "app.not_found":      "Программа не найдена. Аргументы: query",
    "app.launch_failed":  "Программа найдена, но не запустилась. Аргументы: app",

    # напоминания
    "reminder.create":    "Создать напоминание. Аргументы: kind, seconds или at, text",
    "reminder.list":      "Показать запланированное. Аргументы: empty",
    "reminder.cancel":    "Отменить запланированное. Аргументы: empty, count",

    # система
    "system.action":      "Выполнить системное действие. Аргументы: action",
    "system.confirm":     "Опасное действие, нужно подтверждение. Аргументы: action",
    "command.confirm":    "Пользовательская команда опасна, нужно подтверждение",

    # ответы
    "calc":               "Арифметика. Аргументы: result",
    "calc.zero_division": "Деление на ноль",
    "websearch":          "Явный поиск в интернете. Аргументы: query",
    "builtin.answer":     "Встроенный ответ. Аргументы: topic",

    # диалог
    "ask.wake":           "Прозвучало слово активации без команды",
    "cancelled":          "Пользователь отказался от предложенного",
    "silence":            "Ничего не делаем и молчим",

    # хвост конвейера
    "llm.answer":         "Ответила языковая модель. Аргументы: text",
    "fallback.search":    "Не разобрали — ищем в интернете. Аргументы: query",
    "fallback.none":      "Не разобрали и не ищем",

    # служебное
    "plugin":             "Фразу забрал плагин. Аргументы: plugin_id",
    "user_command":       "Сработала пользовательская команда. Аргументы: command_id",
    "unknown":            "Классифицировать не удалось — дефект разбора или прогонщика",
}

#: Намерения, после которых ядро ждёт ответа пользователя.
PENDING_INTENTS = frozenset({"app.ambiguous", "system.confirm",
                             "command.confirm"})


def _frozen(mapping):
    """
    Словарь, который нельзя изменить.

    `frozen=True` у dataclass запрещает переприсваивать поля, но не мешает
    менять словарь внутри поля. Без этого «неизменяемый» Intent можно было
    молча испортить по дороге — ровно то, ради чего он и вводился.
    """
    return MappingProxyType(dict(mapping or {}))


class UnknownIntent(ValueError):
    """Имя намерения нет в каталоге."""


def check_intent_name(name):
    """Проверенное имя или UnknownIntent.

    Опечатка в имени намерения иначе прошла бы молча и превратилась в
    расхождение, которое ищут глазами.
    """
    if name not in INTENTS:
        raise UnknownIntent(f"неизвестное намерение: {name!r}")
    return name


# ---------------------------------------------------------------------------
# Типы
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Intent:
    """
    Что хотел пользователь.

    Неизменяемый: намерение — это вывод разбора, и переписывать его по дороге
    означает потерять то, что было решено. Изменённая копия — through `with_`.
    """

    name: str
    args: dict = field(default_factory=dict)
    # Насколько уверен разбор. Правила дают 1.0; шаг для языковой модели
    # (4.0-B02) будет давать меньше, и по этому числу можно будет решать,
    # переспрашивать ли.
    confidence: float = 1.0
    # Какой шаг конвейера произвёл намерение — для журнала и отладки.
    stage: str = ""
    # Исходная фраза. Нужна, чтобы объяснить решение (4.0b-B04, «Почему?»).
    text: str = ""

    def __post_init__(self):
        check_intent_name(self.name)
        object.__setattr__(self, "args", _frozen(self.args))

    @property
    def needs_answer(self):
        """Ждёт ли ядро ответа пользователя после этого намерения."""
        return self.name in PENDING_INTENTS

    def arg(self, key, default=None):
        return self.args.get(key, default)

    def with_(self, **changes):
        """Копия с изменёнными полями."""
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
    Что надо сделать. Описание, а не вызов.

    Отделено от Intent, потому что одно намерение может дать разные действия:
    «выключи компьютер» — это либо вопрос, либо выключение, смотря был ли
    подтверждён. И потому, что действие можно показать до исполнения — это
    основа предпросмотра опасных операций (4.0-C05).
    """

    kind: str
    args: dict = field(default_factory=dict)
    #: Нужен ли действительный confirmation_id (см. протокол, §11).
    confirm_required: bool = False
    #: Разрешения, которых требует действие (4.0-C04).
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
    Что получилось.

    `response` — то, что Рина скажет; `error_code` — то, по чему ветвится
    логика. Разделены по той же причине, что в каталоге ошибок протокола:
    текст переводится, код — нет.
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
    Проверяет, что объект переживёт дорогу по протоколу.

    Правило протокола: всё сериализуемо, исключений нет. Тип, который нельзя
    записать в JSON, обнаружится здесь, а не при первом запуске двух процессов.
    """
    json.dumps(obj.to_dict(), ensure_ascii=False)
    return True
