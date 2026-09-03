"""
Реестр инструментов: что Рина умеет делать и на каких условиях.

Задачи плана 4.0-C01 (модель) и 4.0-C02 (валидация аргументов).

Инструмент — это описанное действие. У описания семь частей, и каждая
отвечает на вопрос, который иначе решался бы по месту и по-разному:

    имя                 как его назвать в протоколе и в журнале
    схема аргументов    что можно передать и в каком виде
    разрешения          что нужно позволить, чтобы это выполнилось
    confirm_required    надо ли спрашивать человека каждый раз
    форма результата    что вернётся при успехе
    каталог ошибок      чем это может закончиться, кроме успеха
    идемпотентность     безопасно ли повторить

**Зачем описывать, а не просто вызывать.** Сегодня реестр даёт чистую границу
между ядром и оболочкой: оболочка узнаёт список умений, не читая код ядра.
Завтра тем же списком пользуется языковая модель — и тогда описание перестаёт
быть документацией и становится защитой. Модель ошибается в именах и в
аргументах чаще, чем человек; проверка по схеме — первое, обо что эта ошибка
разбивается, ещё до исполнения.

Отсюда строгость, которая иначе выглядела бы избыточной: **лишний аргумент —
ошибка, а не то, что молча игнорируется.** Пропущенный лишний аргумент значит,
что вызывающая сторона считала, будто просит одно, а получит другое.

Qt здесь нет: модуль лежит в ядре.
"""

from dataclasses import dataclass, field
from typing import Any

from core.permissions import check_permission, dangerous


# ---------------------------------------------------------------------------
# Ошибки
# ---------------------------------------------------------------------------
#: Коды, которыми отвечает сам реестр. Остальные коды принадлежат инструментам
#: и перечислены в их описаниях. Полный каталог с категориями и признаком
#: «можно ли повторить» сводит 4.0-D05; здесь — то, без чего не работает C02.
ERROR_UNKNOWN_TOOL = "tool.unknown"
ERROR_INVALID_ARGUMENTS = "tool.invalid_arguments"
ERROR_PERMISSION_DENIED = "permission.denied"
ERROR_CONFIRMATION_REQUIRED = "confirmation.required"


class ToolError(Exception):
    """Ошибка реестра. Несёт код, пригодный для протокола."""

    code = "internal"

    def __init__(self, message, code=None, details=None):
        super().__init__(message)
        self.message = message
        self.code = code or self.code
        self.details = details or {}


class UnknownTool(ToolError):
    code = ERROR_UNKNOWN_TOOL


class InvalidArguments(ToolError):
    code = ERROR_INVALID_ARGUMENTS


# ---------------------------------------------------------------------------
# Схема аргументов
# ---------------------------------------------------------------------------
#: Типы, которые может нести аргумент. Ограничены намеренно: всё, что уедет
#: по протоколу, обязано быть JSON-совместимым (PROTOCOL-v1, §1).
TYPES = {
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "array": list,
    "object": dict,
}


@dataclass(frozen=True)
class Param:
    """Один аргумент инструмента."""

    name: str
    type: str
    description: str
    required: bool = True
    #: Допустимые значения. Пустой набор — любые.
    choices: tuple = ()
    minimum: Any = None
    maximum: Any = None
    default: Any = None

    def __post_init__(self):
        if self.type not in TYPES:
            raise ValueError(f"{self.name}: неизвестный тип {self.type!r}")
        object.__setattr__(self, "choices", tuple(self.choices))

    def to_dict(self):
        """Описание для протокола и для function-calling (N-C01)."""
        out = {"name": self.name, "type": self.type,
               "description": self.description, "required": self.required}
        if self.choices:
            out["choices"] = list(self.choices)
        if self.minimum is not None:
            out["minimum"] = self.minimum
        if self.maximum is not None:
            out["maximum"] = self.maximum
        if self.default is not None:
            out["default"] = self.default
        return out


@dataclass(frozen=True)
class Tool:
    """Описанное действие."""

    name: str
    summary: str
    params: tuple = ()
    #: Что нужно позволить. Пустой набор — ничего.
    permissions: frozenset = frozenset()
    #: Спрашивать человека при каждом вызове.
    confirm_required: bool = False
    #: Безопасно ли повторить с теми же аргументами.
    idempotent: bool = False
    #: Что вернётся при успехе — словами, для описания и для протокола.
    returns: str = ""
    #: Чем может закончиться, кроме успеха.
    errors: tuple = ()

    def __post_init__(self):
        object.__setattr__(self, "params", tuple(self.params))
        object.__setattr__(self, "errors", tuple(self.errors))
        perms = frozenset(check_permission(p) for p in self.permissions)
        object.__setattr__(self, "permissions", perms)

        names = [p.name for p in self.params]
        if len(names) != len(set(names)):
            raise ValueError(f"{self.name}: повторяющиеся имена аргументов")

        # Опасное разрешение обязано требовать подтверждения. Иначе
        # «опасное» — просто пометка в каталоге, ни на что не влияющая.
        if dangerous(perms) and not self.confirm_required:
            raise ValueError(
                f"{self.name}: требует опасного разрешения, значит обязан "
                f"иметь confirm_required=True")

    @property
    def dangerous(self):
        return dangerous(self.permissions)

    def param(self, name):
        for p in self.params:
            if p.name == name:
                return p
        return None

    def to_dict(self):
        return {
            "name": self.name,
            "summary": self.summary,
            "params": [p.to_dict() for p in self.params],
            "permissions": sorted(self.permissions),
            "confirm_required": self.confirm_required,
            "idempotent": self.idempotent,
            "returns": self.returns,
            "errors": list(self.errors),
        }


# ---------------------------------------------------------------------------
# Валидация (4.0-C02)
# ---------------------------------------------------------------------------
def validate(tool, args):
    """
    Проверенные аргументы или InvalidArguments.

    Возвращает НОВЫЙ словарь: подставленные значения по умолчанию и
    приведённые числа не должны просачиваться обратно к вызывающему.

    Сообщение об ошибке пишется так, чтобы по нему можно было исправиться
    с первой попытки: что не так, у какого аргумента, и что ожидалось.
    Позже по нему будет исправляться языковая модель (5.0-C05), и «invalid
    argument» ей не поможет.
    """
    args = dict(args or {})
    known = {p.name for p in tool.params}

    unexpected = sorted(set(args) - known)
    if unexpected:
        raise InvalidArguments(
            f"{tool.name}: неизвестные аргументы: {', '.join(unexpected)}. "
            f"Ожидаются: {', '.join(sorted(known)) or '(нет)'}",
            details={"unexpected": unexpected, "expected": sorted(known)})

    clean = {}
    for param in tool.params:
        if param.name not in args:
            if param.required:
                raise InvalidArguments(
                    f"{tool.name}: пропущен обязательный аргумент "
                    f"«{param.name}» ({param.description})",
                    details={"missing": param.name})
            if param.default is not None:
                clean[param.name] = param.default
            continue

        clean[param.name] = _check_value(tool, param, args[param.name])

    return clean


def _check_value(tool, param, value):
    expected = TYPES[param.type]

    # bool — подкласс int, поэтому «истина» прошла бы как целое число.
    if param.type in ("integer", "number") and isinstance(value, bool):
        raise InvalidArguments(
            f"{tool.name}: «{param.name}» ожидает {param.type}, "
            f"а получено логическое значение",
            details={"param": param.name, "expected": param.type})

    if not isinstance(value, expected):
        raise InvalidArguments(
            f"{tool.name}: «{param.name}» ожидает {param.type}, "
            f"а получено {type(value).__name__}",
            details={"param": param.name, "expected": param.type,
                     "got": type(value).__name__})

    if param.choices and value not in param.choices:
        raise InvalidArguments(
            f"{tool.name}: «{param.name}» должен быть одним из "
            f"{', '.join(map(str, param.choices))}, а получено {value!r}",
            details={"param": param.name, "choices": list(param.choices)})

    if param.minimum is not None and value < param.minimum:
        raise InvalidArguments(
            f"{tool.name}: «{param.name}» не меньше {param.minimum}, "
            f"а получено {value}",
            details={"param": param.name, "minimum": param.minimum})

    if param.maximum is not None and value > param.maximum:
        raise InvalidArguments(
            f"{tool.name}: «{param.name}» не больше {param.maximum}, "
            f"а получено {value}",
            details={"param": param.name, "maximum": param.maximum})

    return value


# ---------------------------------------------------------------------------
# Реестр
# ---------------------------------------------------------------------------
class ToolRegistry:
    """Все известные инструменты."""

    def __init__(self, tools=()):
        self._tools = {}
        for tool in tools:
            self.register(tool)

    def register(self, tool):
        if tool.name in self._tools:
            raise ValueError(f"инструмент {tool.name!r} уже зарегистрирован")
        self._tools[tool.name] = tool
        return tool

    def get(self, name):
        tool = self._tools.get(name)
        if tool is None:
            raise UnknownTool(
                f"неизвестный инструмент: {name!r}",
                details={"known": sorted(self._tools)})
        return tool

    def forget(self, name):
        """
        Убрать инструмент. Нужно выключению плагина (`4.0-H03`).

        Выключенный плагин обязан унести свои инструменты с собой: реестр,
        помнящий инструмент выключенного плагина, однажды его вызовет.
        """
        return self._tools.pop(name, None)

    def has(self, name):
        return name in self._tools

    def names(self):
        return sorted(self._tools)

    def all(self):
        return [self._tools[n] for n in self.names()]

    def validate(self, name, args):
        """Проверить вызов, ничего не выполняя."""
        return validate(self.get(name), args)

    def describe(self):
        """Весь реестр словарями — для протокола и для function-calling."""
        return [tool.to_dict() for tool in self.all()]

    def requiring(self, permission):
        """Кто просит это разрешение — для экрана разрешений и для тестов."""
        return [t for t in self.all() if permission in t.permissions]

    def __len__(self):
        return len(self._tools)

    def __contains__(self, name):
        return name in self._tools
