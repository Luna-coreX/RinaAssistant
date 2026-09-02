"""
Каталог ошибок: ошибка как часть контракта, а не как исключительная ситуация.

Задачи плана `4.0-D05` (каталог) и часть `4.0-D04`; спецификация, §5.

**Код и текст разделены намеренно.** Логика ветвится по `code`, человек читает
`message`. Код стабилен между версиями и языками, текст переводится и
переформулируется; если бы ветвление шло по тексту, перевод ломал бы
поведение.

**Категория и признак повтора принадлежат коду, а не месту вызова.** Одна и та
же ошибка, поднятая из двух мест, обязана одинаково отвечать на вопросы «кто
виноват» и «есть ли смысл повторить»; поэтому вызывающая сторона передаёт код и
текст, а остальное берётся отсюда. Иначе `app.not_found` однажды окажется
`system` и неповторяемой в одном месте и `user` с повтором в другом, и оболочка
станет вести себя по-разному в зависимости от того, каким путём пришла ошибка.

**`retryable` значит «имеет ли смысл повторить то же самое».** Не «поможет ли
что-нибудь»: просроченное подтверждение неповторяемо, потому что тот же вызов с
тем же идентификатором провалится снова, — а вот получить новое подтверждение и
позвать заново, разумеется, можно.

Каталог сверяется с тем, что ядро действительно умеет отправлять
(`tools/test_wire.py`): каждый код, объявленный любым инструментом реестра,
обязан здесь быть. Список, который пишут руками и не сверяют, расходится с
кодом на первом же новом инструменте.
"""

from dataclasses import dataclass, field
from typing import Any

#: Категории из §5. `user` — человек может исправить сам; `system` — виновато
#: окружение; `protocol` — дефект одной из сторон, и его чинят программисты.
CATEGORIES = ("user", "system", "protocol")


@dataclass(frozen=True)
class ErrorSpec:
    """Строка каталога: чем ошибка является, независимо от места вызова."""

    code: str
    category: str
    retryable: bool
    note: str = ""


def _spec(code, category, retryable, note=""):
    return ErrorSpec(code, category, retryable, note)


#: Полный каталог. Дополняется вместе со спецификацией, а не в обход неё.
CATALOGUE: dict[str, ErrorSpec] = {s.code: s for s in (
    # --- протокол: дефект одной из сторон -----------------------------------
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

    # --- права и подтверждения ----------------------------------------------
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

    # --- реестр инструментов ------------------------------------------------
    _spec("tool.unknown", "protocol", False,
          "вызвана несуществующая возможность"),
    _spec("tool.invalid_arguments", "protocol", False,
          "аргументы не проходят схему инструмента"),

    # --- настройки ----------------------------------------------------------
    _spec("settings.unknown_key", "protocol", False,
          "такой настройки нет"),
    _spec("settings.invalid_value", "user", False,
          "значение не проходит ограничения ключа"),
    _spec("llm.remote_address", "user", True,
          "адрес модели не локальный: разговоры уйдут на чужую машину; "
          "значение принято, но человека предупреждают"),

    # --- программы ----------------------------------------------------------
    _spec("app.not_found", "user", False,
          "программа не найдена в индексе"),
    _spec("app.launch_failed", "system", True,
          "запуск сорвался; со второй попытки бывает иначе"),

    # --- речь и модель ------------------------------------------------------
    _spec("stt.unavailable", "system", False,
          "распознавания нет: модель не установлена или не загрузилась"),
    _spec("stt.failed", "system", True,
          "распознать не удалось"),
    _spec("tts.unavailable", "system", False,
          "синтеза нет"),
    _spec("llm.unavailable", "system", True,
          "модель недоступна: сеть, адрес, запущенный сервер"),

    # --- задачи -------------------------------------------------------------
    _spec("task.cancelled", "user", False,
          "задача снята по просьбе человека"),

    # --- инструменты со своими исходами -------------------------------------
    _spec("calc.zero_division", "user", False,
          "деление на ноль в выражении"),

    # --- последнее прибежище ------------------------------------------------
    _spec("internal", "system", True,
          "непредусмотренный сбой; подробности — в журнале"),
)}


@dataclass(frozen=True)
class ProtocolError:
    """Полезная нагрузка сообщения типа `error` (§5)."""

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
    Ошибка контракта, обнаруженная на этой стороне.

    Несёт готовую `ProtocolError`: то, что уходит собеседнику, и то, что
    поднимается по стеку, — одно и то же значение. Иначе текст в журнале и
    текст в канале разошлись бы, и отладка двухпроцессной системы стала бы
    сверкой двух разных описаний одного события.
    """

    def __init__(self, error: ProtocolError):
        super().__init__(f"{error.code}: {error.message}")
        self.error = error


def make(code: str, message: str, **details) -> ProtocolError:
    """Собрать ошибку по коду: категория и повтор берутся из каталога."""
    spec = CATALOGUE.get(code)
    if spec is None:
        raise ValueError(
            f"код {code!r} не объявлен в каталоге. Новый код заводится в "
            "спецификации и здесь, а не по месту вызова")
    return ProtocolError(code=spec.code, category=spec.category,
                         retryable=spec.retryable, message=message,
                         details=details)


def fault(code: str, message: str, **details) -> ProtocolFault:
    """То же, но готовое к `raise`."""
    return ProtocolFault(make(code, message, **details))


# --- имена кодов, которыми пользуется сам пакет ------------------------------
ERROR_INCOMPATIBLE = "protocol.incompatible"
ERROR_UNKNOWN_METHOD = "protocol.unknown_method"
ERROR_FRAME_TOO_LARGE = "protocol.frame_too_large"
ERROR_NOT_READY = "protocol.not_ready"
ERROR_INVALID_ENVELOPE = "protocol.invalid_envelope"
ERROR_INVALID_PAYLOAD = "protocol.invalid_payload"
ERROR_INVALID_STATE = "protocol.invalid_state"
