"""
The tool registry: what Rina can do and on what terms.

Plan items 4.0-C01 (the model) and 4.0-C02 (argument validation).

A tool is a described action. The description has seven parts, and each
answers a question that would otherwise be settled on the spot and
differently every time:

    the name             what to call it in the protocol and the journal
    the argument schema  what may be passed and in what form
    the permissions      what has to be allowed for this to be performed
    confirm_required     whether to ask the person every time
    the result's shape   what comes back on success
    the error catalogue  how this may end other than in success
    idempotence          whether it is safe to repeat

**Why describe rather than simply call.** Today the registry gives a clean
boundary between the core and the shell: the shell learns the list of skills
without reading the core's code. Tomorrow a language model uses that same
list — and then the description stops being documentation and becomes a
defence. A model gets names and arguments wrong more often than a person
does; the schema check is the first thing that mistake breaks against, still
before execution.

Hence a strictness that would otherwise look excessive: **a surplus argument
is an error, not something silently ignored.** A surplus argument let
through means the calling side believed it was asking for one thing and will
get another.

There is no Qt here: the module lies in the core.
"""

from dataclasses import dataclass, field
from typing import Any

from core.permissions import check_permission, dangerous


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------
#: The codes the registry itself answers with. The other codes belong to the
#: tools and are listed in their descriptions. The full catalogue with
#: categories and a "may this be retried" mark is brought together by
#: 4.0-D05; here is what C02 cannot work without.
ERROR_UNKNOWN_TOOL = "tool.unknown"
ERROR_INVALID_ARGUMENTS = "tool.invalid_arguments"
ERROR_PERMISSION_DENIED = "permission.denied"
ERROR_CONFIRMATION_REQUIRED = "confirmation.required"


class ToolError(Exception):
    """A registry error. Carries a code fit for the protocol."""

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
# The argument schema
# ---------------------------------------------------------------------------
#: The types an argument may carry. Limited deliberately: everything that
#: will travel over the protocol is obliged to be JSON-compatible
#: (PROTOCOL-v1, §1).
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
    """One argument of a tool."""

    name: str
    type: str
    description: str
    required: bool = True
    #: The permissible values. An empty set means any.
    choices: tuple = ()
    minimum: Any = None
    maximum: Any = None
    default: Any = None

    def __post_init__(self):
        if self.type not in TYPES:
            raise ValueError(f"{self.name}: неизвестный тип {self.type!r}")
        object.__setattr__(self, "choices", tuple(self.choices))

    def to_dict(self):
        """A description for the protocol and for function calling (N-C01)."""
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
    """A described action."""

    name: str
    summary: str
    params: tuple = ()
    #: What has to be allowed. An empty set means nothing.
    permissions: frozenset = frozenset()
    #: Ask the person on every call.
    confirm_required: bool = False
    #: Whether it is safe to repeat with the same arguments.
    idempotent: bool = False
    #: What comes back on success — in words, for the description and for the protocol.
    returns: str = ""
    #: How it may end other than in success.
    errors: tuple = ()

    def __post_init__(self):
        object.__setattr__(self, "params", tuple(self.params))
        object.__setattr__(self, "errors", tuple(self.errors))
        perms = frozenset(check_permission(p) for p in self.permissions)
        object.__setattr__(self, "permissions", perms)

        names = [p.name for p in self.params]
        if len(names) != len(set(names)):
            raise ValueError(f"{self.name}: повторяющиеся имена аргументов")

        # A dangerous permission is obliged to require confirmation.
        # Otherwise "dangerous" is merely a mark in the catalogue, affecting
        # nothing.
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
# Validation (4.0-C02)
# ---------------------------------------------------------------------------
def validate(tool, args):
    """
    Checked arguments, or InvalidArguments.

    Returns a NEW dict: substituted defaults and coerced numbers must not
    leak back to the caller.

    The error message is written so that one can correct oneself from it on
    the first attempt: what is wrong, in which argument, and what was
    expected. Later a language model will correct itself by it (5.0-C05),
    and "invalid argument" will not help it.
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

    # bool is a subclass of int, so "true" would pass as a whole number.
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
# The registry
# ---------------------------------------------------------------------------
class ToolRegistry:
    """Every known tool."""

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
        Remove a tool. Needed when a plugin is switched off (`4.0-H03`).

        A switched-off plugin is obliged to take its tools with it: a
        registry that remembers a switched-off plugin's tool will call it
        one day.
        """
        return self._tools.pop(name, None)

    def has(self, name):
        return name in self._tools

    def names(self):
        return sorted(self._tools)

    def all(self):
        return [self._tools[n] for n in self.names()]

    def validate(self, name, args):
        """Check a call without performing anything."""
        return validate(self.get(name), args)

    def describe(self):
        """The whole registry as dicts — for the protocol and for function calling."""
        return [tool.to_dict() for tool in self.all()]

    def requiring(self, permission):
        """Who asks for this permission — for the permissions screen and for the tests."""
        return [t for t in self.all() if permission in t.permissions]

    def __len__(self):
        return len(self._tools)

    def __contains__(self, name):
        return name in self._tools
