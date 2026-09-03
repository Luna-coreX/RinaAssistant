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

from core.settings_store import DEFAULTS, GROUPS

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
    #: Ключ больше не участвует, но данные не стёрты. Оболочка его не
    #: показывает; удалять из хранилища нечего и незачем.
    obsolete: bool = False
    #: Набор значений известен ядру, но не заранее: какие голоса
    #: установлены, какие движки доступны. Оболочка спрашивает списком
    #: через `settings.options`.
    dynamic: bool = False
    #: Значение — путь. Чем именно его выбирать (окно выбора папки или
    #: файла) решает оболочка; ядро говорит только, что это путь.
    format: str = ""
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

    # Набор значений известен ядру, но зависит от установленного: какие
    # движки собрались, какие голоса нашлись. Статическим перечислением
    # это не выразить — оболочка спросит списком.
    "tts_engine": Constraint(dynamic=True),
    "stt_engine": Constraint(dynamic=True),
    "voice": Constraint(dynamic=True),
    "whisper_model": Constraint(dynamic=True),

    # Пути к моделям. Чем выбирать — дело оболочки; ядро говорит лишь,
    # что это путь, а не имя.
    "vosk_model": Constraint(format="folder"),
    # Список папок состоит из путей: оболочке этого хватит, чтобы предложить
    # выбор папки, а не поле, куда путь набирают руками с опечаткой.
    "program_folders": Constraint(format="folder"),
    "piper_model": Constraint(format="file"),
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

    # Отделка меняется на лету: обе равноправны, и подменяется целый словарь
    # ресурсов, а не пересчитываются цвета от базового. Перезапуска не
    # требует — а требовать его значило бы соврать о том, как это устроено.
    "finish": Constraint(choices=("silver", "black")),

    # Язык меняется редко и затрагивает окно целиком.
    # Языки перечисляет ядро: список знает `core.i18n`, и он же меняется
    # от того, какие переводы собраны. Перезапуск больше не нужен — с
    # 4.0-F08 язык применяется сразу обеими сторонами: ядро переключает
    # реплики Рины, оболочка — слова интерфейса.
    "ui_language": Constraint(dynamic=True),

    # Пять заимствованных палитр 3.1.0. Заменены двумя отделками (4.0-R08);
    # значения остаются в хранилище, но наружу не отдаются.
    "theme": Constraint(obsolete=True),
    "accent": Constraint(obsolete=True),

    # Служебное: не настройки, а состояние хранилища.
    "config_version": Constraint(secret=True),
    "first_run": Constraint(secret=True),

    # Слово активации в единственном числе — форма 3.1.0, зеркало первого
    # из `wake_words`. Хранилище её пишет для совместимости, показывать её
    # рядом со списком значило бы предлагать человеку править одно и то же
    # дважды и по-разному.
    "wake_word": Constraint(obsolete=True),
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
    if rule.obsolete:
        out["obsolete"] = True
    if rule.dynamic:
        out["dynamic"] = True
    if rule.format:
        out["format"] = rule.format
    return out


#: Что вообще является настройкой.
#:
#: Хранилище держит в одном файле и настройки, и данные: команды, историю,
#: напоминания, состояние плагинов. Для хранилища это одно и то же — ключ и
#: значение, — но для человека нет: «история» не настройка, и показывать её
#: полем на экране настроек бессмысленно.
#:
#: Выяснилось это, когда экран настроек построился впервые: в секции «Прочее»
#: оказались история, команды и напоминания. Схема описывает **группу
#: настроек**, а не весь файл.
SETTABLE = tuple(GROUPS["settings"])


def describe(keys=None) -> dict[str, dict[str, Any]]:
    """Схема целиком или по перечисленным ключам."""
    names = list(keys) if keys else list(SETTABLE)
    return {key: describe_key(key) for key in names if key in SETTABLE}


def options_for(key: str, settings) -> list[dict[str, Any]]:
    """
    Какие значения ключ принимает **сейчас**, на этой машине.

    Отвечает ядро, потому что знает только оно: какие движки собрались,
    какие голоса установлены. Оболочка это перечислить не может — у неё
    нет ни моделей, ни их каталогов.

    **Имя вещи приходит оттуда, где вещь живёт.** «Vosk (офлайн)» —
    название движка, часть того, чем движок является, как «Discord» —
    название программы в индексе. Строка интерфейса — это «Слова
    активации»; она по-прежнему в оболочке (`4.0-F08`). Граница проходит
    между именами вещей и словами интерфейса, а не между процессами.
    """
    from voice import stt, tts

    if key == "tts_engine":
        return [{"value": i, "title": t, "available": bool(a)}
                for i, t, a in tts.engine_choices()]
    if key == "stt_engine":
        return [{"value": i, "title": t, "available": bool(a)}
                for i, t, a in stt.engine_choices()]
    if key == "voice":
        engine = tts.get_engine(str(settings.get("tts_engine", "silent")))
        return [{"value": i, "title": t, "available": True}
                for i, t in engine.voices()]
    if key == "ui_language":
        # Доля перевода не называется числом нарочно: ядро знает только
        # свою половину — реплики Рины, — а слова интерфейса переводит
        # оболочка и считает их сама (ADR 0007). Одно число на две
        # половины было бы точностью, которой нет.
        from core.i18n import LANGUAGES, coverage
        return [{"value": name,
                 "title": (name if coverage(name) >= 0.99
                           else f"{name} — перевод неполный"),
                 "available": True}
                for name in LANGUAGES]
    if key == "whisper_model":
        # Перечень моделей Whisper фиксирован и известен без установки:
        # это имена, а не найденные файлы.
        return [{"value": name, "title": title, "available": True}
                for name, title in (("tiny", "tiny — самая быстрая"),
                                    ("base", "base — по умолчанию"),
                                    ("small", "small"),
                                    ("medium", "medium"),
                                    ("large", "large — самая точная"))]
    return []


def validate(key: str, value: Any, settings=None) -> tuple[bool, str, str]:
    """
    Проверить значение. Возвращает (принято, код, пояснение).

    Код — из каталога `4.0-D05`, чтобы оболочка ветвилась по нему, а не по
    тексту. Пустой код при `принято=True` значит «всё в порядке»; непустой —
    что значение принято, но о нём стоит предупредить.
    """
    if key not in SETTABLE:
        # Данные тоже лежат в хранилище, но настройками не являются:
        # «история» не то, что настраивают полем.
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

    # Динамический набор проверяется по тому, что есть сейчас: список
    # «какие голоса установлены» вчерашним быть не может.
    if rule.dynamic:
        allowed = {o["value"] for o in options_for(key, settings or {})}
        if allowed and value not in allowed:
            return False, "settings.invalid_value", \
                f"«{key}»: такого значения сейчас нет."

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
