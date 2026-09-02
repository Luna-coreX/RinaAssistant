"""
Ошибка как часть контракта, а не как исключительная ситуация.

Спецификация, §5. Полный каталог кодов сводит `4.0-D05`; здесь — форма
ошибки и те коды, без которых не работают конверт и рукопожатие.

**Код и текст разделены намеренно.** Логика ветвится по `code`, человек
читает `message`. Код стабилен между версиями и языками, текст переводится
и переформулируется; если бы ветвление шло по тексту, перевод ломал бы
поведение.

**Найдено при реализации: в каталоге спецификации не хватало одного кода.**
Требование §15.1 гласит, что отсутствие обязательного поля конверта — ошибка
категории `protocol`, но кода для неё в §5 нет. Добавлен
`protocol.invalid_envelope`; `4.0-D05` обязан внести его в каталог, а не
переоткрывать заново.
"""

from dataclasses import dataclass, field
from typing import Any

#: Категории из §5. `user` — человек может исправить сам; `system` — виновато
#: окружение; `protocol` — дефект одной из сторон, и его чинят программисты.
CATEGORIES = ("user", "system", "protocol")

# --- коды, которыми пользуются конверт и рукопожатие (§5) ---
ERROR_INCOMPATIBLE = "protocol.incompatible"
ERROR_UNKNOWN_METHOD = "protocol.unknown_method"
ERROR_FRAME_TOO_LARGE = "protocol.frame_too_large"
ERROR_NOT_READY = "protocol.not_ready"
#: Дополнение к каталогу §5, см. заголовок модуля.
ERROR_INVALID_ENVELOPE = "protocol.invalid_envelope"

#: Признак «имеет ли смысл повторить то же самое» — часть контракта, а не
#: догадка вызывающей стороны. Для протокольных ошибок повтор бессмысленен
#: везде, кроме `not_ready`: там собеседник просто ещё не поздоровался.
_RETRYABLE = {
    ERROR_INCOMPATIBLE: False,
    ERROR_UNKNOWN_METHOD: False,
    ERROR_FRAME_TOO_LARGE: False,
    ERROR_NOT_READY: True,
    ERROR_INVALID_ENVELOPE: False,
}


@dataclass(frozen=True)
class ProtocolError:
    """Полезная нагрузка сообщения типа `error`."""

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
    Нарушение протокола, обнаруженное на этой стороне.

    Несёт готовую `ProtocolError`: то, что уходит собеседнику, и то, что
    поднимается по стеку, — одно и то же значение. Иначе текст в журнале и
    текст в канале разошлись бы, и отладка двухпроцессной системы стала бы
    сверкой двух разных описаний одного события.
    """

    def __init__(self, error: ProtocolError):
        super().__init__(f"{error.code}: {error.message}")
        self.error = error


def protocol_fault(code: str, message: str, **details) -> ProtocolFault:
    """Собрать протокольную ошибку по коду: категория и повтор — из таблицы."""
    if code not in _RETRYABLE:
        raise ValueError(f"код не объявлен в модуле ошибок: {code!r}")
    return ProtocolFault(ProtocolError(
        code=code,
        category="protocol",
        retryable=_RETRYABLE[code],
        message=message,
        details=details,
    ))
