"""
The error catalogue: an error as part of the contract, not as an exceptional
situation.

Plan items `4.0-D05` (the catalogue) and part of `4.0-D04`; specification,
§5.

**The code and the text are separated deliberately.** Logic branches on
`code`, a person reads `message`. The code is stable across versions and
languages, the text is translated and reworded; if branching went by the
text, translation would break behaviour.

**The category and the retry mark belong to the code, not to the call
site.** One and the same error raised from two places must answer the
questions "whose fault is it" and "is there any point retrying" in the same
way; so the caller passes the code and the text, and the rest is taken from
here. Otherwise `app.not_found` will one day be `system` and non-retryable
in one place and `user` with a retry in another, and the shell will start
behaving differently depending on which way the error arrived.

**`retryable` means "is there any point repeating the same thing".** Not
"will anything help": an expired confirmation is non-retryable, because the
same call with the same identifier will fail again — while getting a fresh
confirmation and calling again is of course possible.

The catalogue is checked against what the core can actually send
(`tools/test_wire.py`): every code declared by any tool in the registry must
be here. A list that is written by hand and never checked parts company with
the code at the very first new tool.
"""

from dataclasses import dataclass, field
from typing import Any

#: The categories from §5. `user` — the person can put it right themselves;
#: `system` — the environment is at fault; `protocol` — a defect in one of
#: the sides, and programmers are the ones who fix it.
CATEGORIES = ("user", "system", "protocol")


@dataclass(frozen=True)
class ErrorSpec:
    """A catalogue row: what an error is, independently of the call site."""

    code: str
    category: str
    retryable: bool
    note: str = ""


def _spec(code, category, retryable, note=""):
    return ErrorSpec(code, category, retryable, note)


#: The full catalogue. Extended together with the specification, not around it.
CATALOGUE: dict[str, ErrorSpec] = {s.code: s for s in (
    # --- protocol: a defect in one of the sides -----------------------------
    _spec("protocol.incompatible", "protocol", False,
          "общей версии протокола нет"),
    _spec("protocol.unknown_method", "protocol", False,
          "метода нет либо его возможность не объявлена"),
    _spec("protocol.frame_too_large", "protocol", False,
          "кадр больше предела канала"),
    _spec("protocol.not_ready", "protocol", True,
          "рукопожатие ещё не состоялось; позже тот же вызов пройдёт"),
    _spec("protocol.invalid_envelope", "protocol", False,
          "конверт неполон или не разбирается"),
    _spec("protocol.invalid_payload", "protocol", False,
          "нагрузка не соответствует объявленной форме события"),
    _spec("protocol.invalid_state", "protocol", False,
          "сообщение не к месту: поток закрыт, задача уже завершена"),

    # --- permissions and confirmations --------------------------------------
    _spec("permission.denied", "user", False,
          "разрешение не выдано"),
    _spec("permission.required", "user", False,
          "действие требует разрешения, которого никто не спрашивал"),
    _spec("confirmation.required", "user", False,
          "опасное действие вызвано без подтверждения"),
    _spec("confirmation.invalid", "protocol", False,
          "подтверждение выдано под другой вызов или другие аргументы"),
    _spec("confirmation.expired", "user", False,
          "срок подтверждения истёк; нужно новое, а не повтор того же"),

    # --- the tool registry ---------------------------------------------------
    _spec("tool.unknown", "protocol", False,
          "вызвана несуществующая возможность"),
    _spec("tool.invalid_arguments", "protocol", False,
          "аргументы не проходят схему инструмента"),

    # --- carrying data between machines ---------------------------------------
    #
    # `user`, not `protocol`: picking a history file where commands were
    # asked for is a person choosing the wrong file, not a defect of either
    # side. The category decides how the shell speaks about it, and calling
    # this a protocol defect would tell the person their program is broken.
    _spec("transfer.wrong_kind", "user", False,
          "файл не того вида: это не выгрузка команд"),
    _spec("transfer.too_new", "user", False,
          "файл сделан более новой версией — обновите приложение"),
    _spec("transfer.unreadable", "user", False,
          "файл не разобрать: не похоже на выгрузку Рины"),

    # --- settings -------------------------------------------------------------
    _spec("settings.unknown_key", "protocol", False,
          "такой настройки нет"),
    _spec("settings.invalid_value", "user", False,
          "значение не проходит ограничения ключа"),
    _spec("llm.remote_address", "user", True,
          "адрес модели не локальный: разговоры уйдут на чужую машину; "
          "значение принято, но человека предупреждают"),

    # --- plugins ---------------------------------------------------------------
    _spec("plugin.not_found", "protocol", False,
          "плагина с таким номером нет: список устарел или его удалили"),

    # --- programs --------------------------------------------------------------
    _spec("app.not_found", "user", False,
          "программа не найдена в индексе"),
    _spec("app.launch_failed", "system", True,
          "запуск сорвался; со второй попытки бывает иначе"),

    # --- speech and the model ----------------------------------------------------
    _spec("stt.unavailable", "system", False,
          "распознавания нет: модель не установлена или не загрузилась"),
    _spec("stt.failed", "system", True,
          "распознать не удалось"),
    _spec("tts.unavailable", "system", False,
          "синтеза нет"),
    _spec("llm.unavailable", "system", True,
          "модель недоступна: сеть, адрес, запущенный сервер"),

    # --- tasks ---------------------------------------------------------------
    _spec("task.cancelled", "user", False,
          "задача снята по просьбе человека"),

    # --- tools with outcomes of their own -------------------------------------
    _spec("calc.zero_division", "user", False,
          "деление на ноль в выражении"),

    # --- the last resort ------------------------------------------------------
    _spec("internal", "system", True,
          "непредусмотренный сбой; подробности — в журнале"),
)}


@dataclass(frozen=True)
class ProtocolError:
    """The payload of a message of type `error` (§5)."""

    code: str
    category: str
    retryable: bool
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.category not in CATEGORIES:
            raise ValueError(f"неизвестная категория ошибки: {self.category!r}")

    def to_payload(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "category": self.category,
            "retryable": self.retryable,
            "message": self.message,
            "details": dict(self.details),
        }


class ProtocolFault(Exception):
    """
    A contract error discovered on this side.

    It carries a ready-made `ProtocolError`: what goes to the correspondent
    and what is raised up the stack are one and the same value. Otherwise
    the text in the journal and the text in the channel would part company,
    and debugging a two-process system would become a comparison of two
    different descriptions of one event.
    """

    def __init__(self, error: ProtocolError):
        super().__init__(f"{error.code}: {error.message}")
        self.error = error


def make(code: str, message: str, **details) -> ProtocolError:
    """Build an error from a code: the category and the retry come from the catalogue."""
    spec = CATALOGUE.get(code)
    if spec is None:
        raise ValueError(
            f"код {code!r} не объявлен в каталоге. Новый код заводится в "
            "спецификации и здесь, а не по месту вызова")
    return ProtocolError(code=spec.code, category=spec.category,
                         retryable=spec.retryable, message=message,
                         details=details)


def fault(code: str, message: str, **details) -> ProtocolFault:
    """The same, but ready to `raise`."""
    return ProtocolFault(make(code, message, **details))


# --- the names of the codes the package itself uses --------------------------
ERROR_INCOMPATIBLE = "protocol.incompatible"
ERROR_UNKNOWN_METHOD = "protocol.unknown_method"
ERROR_FRAME_TOO_LARGE = "protocol.frame_too_large"
ERROR_NOT_READY = "protocol.not_ready"
ERROR_INVALID_ENVELOPE = "protocol.invalid_envelope"
ERROR_INVALID_PAYLOAD = "protocol.invalid_payload"
ERROR_INVALID_STATE = "protocol.invalid_state"
