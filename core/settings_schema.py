# -*- coding: utf-8 -*-
"""
Схема настроек: смысл значений, но не их вид.

Задача плана `4.0-E06a`, решение — [ADR 0006](../docs/adr/0006-settings-ownership.md).

Ядро владеет смыслом: какой у значения тип, что оно принимает, от чего
зависит, можно ли его показывать и когда изменение вступит в силу. Оболочка
владеет представлением: подписями, группировкой в секции, порядком, поиском.
Граница проходит не между «формой» и «значениями», а между **смыслом и
видом**.

Почему так — коротко. Подписи полей это строки интерфейса, а `4.0-F08` уже
решил, что они живут в оболочке; ядро, описывающее форму, забрало бы их
себе и тихо отменило бы то решение. Десять секций экрана настроек — работа
`4.0-R04`, то есть утверждение о том, как человек садится настраивать
голосового помощника, а не свойство данных.

Но и обратное неверно: только ядро знает, что `llm_model` бессмысленна при
выключенной модели, и что адрес вне `localhost` отправляет разговоры на
чужую машину. Отдать это оболочке — значит завести вторую копию знания на
другом языке, и она разойдётся с первой молча.

**Тип и значение по умолчанию выводятся**, а не переписываются руками: они
уже есть в `DEFAULTS`, и вторая их копия разошлась бы с первой. Руками
описано только то, чего в умолчаниях не видно, — перечисления, диапазоны,
зависимости, секретность и необходимость перезапуска.
"""

from dataclasses import dataclass
from typing import Any

from core.settings_store import DEFAULTS

#: Как питоновский тип значения по умолчанию называется в протоколе.
_TYPE_NAMES = {
    str: "string", bool: "boolean", int: "integer", float: "number",
    dict: "object", list: "array",
}


@dataclass(frozen=True)
class Constraint:
    """Что ядру известно о значении сверх его типа."""

    choices: tuple[Any, ...] = ()
    low: float | None = None
    high: float | None = None
    #: Ключ, при выключенном значении которого этот параметр бессмыслен.
    depends_on: str = ""
    #: Не показывать в открытом виде и не писать в журнал.
    secret: bool = False
    #: Вступает в силу только после перезапуска.
    restart_required: bool = False
    #: Код предупреждения, если значение опасно, но допустимо.
    warn_code: str = ""


#: Только то, чего не видно из умолчаний. Пустая запись здесь не нужна:
#: ключ без ограничений описывается типом и умолчанием, и этого довольно.
CONSTRAINTS: dict[str, Constraint] = {
    "volume": Constraint(low=0, high=100),
    "speed": Constraint(low=50, high=200),
    "wake_sensitivity": Constraint(low=0.0, high=1.0),
    "listen_seconds": Constraint(low=1, high=60),
    "llm_timeout": Constraint(low=1, high=600, depends_on="llm_enabled"),
    "log_level": Constraint(choices=("DEBUG", "INFO", "WARNING", "ERROR")),
    "search_engine": Constraint(choices=("google", "yandex", "duckduckgo",
                                         "bing")),

    # Языковая модель: три поля бессмысленны, пока она выключена.
    "llm_url": Constraint(depends_on="llm_enabled",
                          warn_code="llm.remote_address"),
    "llm_model": Constraint(depends_on="llm_enabled"),
    "llm_persona": Constraint(depends_on="llm_enabled"),

    # Записывать тексты реплик — решение о приватности, и оно имеет силу
    # только при включённой истории.
    "log_texts": Constraint(depends_on="save_history"),

    # Меняются редко и требуют перезапуска: их применение затрагивает окно
    # целиком, а не отдельный экран.
    "ui_language": Constraint(restart_required=True),
    "theme": Constraint(restart_required=True),
    "accent": Constraint(restart_required=True),

    # Служебное: не настройки, а состояние хранилища.
    "config_version": Constraint(secret=True),
    "first_run": Constraint(secret=True),
}


def type_of(key: str) -> str:
    """Тип значения по его умолчанию."""
    return _TYPE_NAMES.get(type(DEFAULTS.get(key)), "string")


def describe_key(key: str) -> dict[str, Any]:
    """Описание одного ключа: тип, умолчание и всё, что о нём известно."""
    rule = CONSTRAINTS.get(key, Constraint())
    out: dict[str, Any] = {"type": type_of(key), "default": DEFAULTS.get(key)}
    if rule.choices:
        out["choices"] = list(rule.choices)
    if rule.low is not None:
        out["low"] = rule.low
    if rule.high is not None:
        out["high"] = rule.high
    if rule.depends_on:
        out["depends_on"] = rule.depends_on
    if rule.secret:
        out["secret"] = True
    if rule.restart_required:
        out["restart_required"] = True
    return out


def describe(keys=None) -> dict[str, dict[str, Any]]:
    """Схема целиком или по перечисленным ключам."""
    names = list(keys) if keys else list(DEFAULTS)
    return {key: describe_key(key) for key in names if key in DEFAULTS}


def validate(key: str, value: Any) -> tuple[bool, str, str]:
    """
    Проверить значение. Возвращает (принято, код, пояснение).

    Код — из каталога `4.0-D05`, чтобы оболочка ветвилась по нему, а не по
    тексту. Пустой код при `принято=True` значит «всё в порядке»; непустой —
    что значение принято, но о нём стоит предупредить.
    """
    if key not in DEFAULTS:
        return False, "settings.unknown_key", f"Нет такой настройки: {key}."

    rule = CONSTRAINTS.get(key, Constraint())
    expected = type_of(key)
    actual = _TYPE_NAMES.get(type(value), "string")
    # bool — подкласс int, и «истина» вместо числа прошла бы молча.
    if expected in ("integer", "number") and isinstance(value, bool):
        return False, "settings.invalid_value", \
            f"«{key}» ожидает число, а не логическое значение."
    if expected == "number" and actual == "integer":
        actual = "number"
    if actual != expected:
        return False, "settings.invalid_value", \
            f"«{key}» ожидает {expected}, получено {actual}."

    if rule.choices and value not in rule.choices:
        return False, "settings.invalid_value", \
            f"«{key}» принимает только: {', '.join(map(str, rule.choices))}."
    if rule.low is not None and value < rule.low:
        return False, "settings.invalid_value", \
            f"«{key}» не может быть меньше {rule.low}."
    if rule.high is not None and value > rule.high:
        return False, "settings.invalid_value", \
            f"«{key}» не может быть больше {rule.high}."

    # Принято, но стоит предупредить. Это знание ядра: только оно знает,
    # для чего этот адрес и что уходит по нему наружу.
    if key == "llm_url" and isinstance(value, str) and value:
        host = value.split("//")[-1].split("/")[0].split(":")[0].lower()
        if host and host not in ("localhost", "127.0.0.1", "::1", "[::1]"):
            return True, "llm.remote_address", (
                "Адрес не локальный: тексты разговоров будут уходить "
                f"на {host}.")

    return True, "", ""
