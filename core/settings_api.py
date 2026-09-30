"""
Интерфейс доступа к настройкам.

Задача плана 4.0-B06. До неё ядро импортировало модульный синглтон
`core.settings_store.settings` и обращалось к нему напрямую из десятка мест.
Три следствия, каждое из которых мешает разделению:

    * два ядра в одном процессе обязаны делить одни настройки;
    * подставить в тесте другие значения можно только подменой модуля;
    * оболочка после разделения не сможет получать настройки по протоколу,
      пока «настройки» означают «этот конкретный файл».

Здесь описано, что именно ядру от настроек нужно. Список намеренно короткий:
всё, чего в нём нет, ядру знать не положено — ни где лежит файл, ни в каком он
формате, ни сколько там групп.

Реализация по умолчанию — тот же `settings_store`, поэтому поведение не
меняется. Смысл не в новой реализации, а в том, что зависимость стала явной.

Qt здесь нет: модуль лежит в ядре.
"""

import contextlib
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class SettingsProvider(Protocol):
    """Минимум, которого ядру достаточно."""

    def get(self, key: str, default: Any = None) -> Any:
        """Значение настройки или default."""
        ...

    def set(self, key: str, value: Any) -> None:
        """Записать значение. На диск не обязательно — см. save()."""
        ...

    def save(self) -> bool:
        """Сохранить изменённое."""
        ...

    def transaction(self):
        """
        Блокировка на всё чтение-изменение-запись.

        Нужна хранилищам истории, напоминаний и статистики: сама
        последовательность «прочитать список — изменить — записать» не
        атомарна, и два потока теряют записи друг друга (см. 3.1.0, R03).
        """
        ...


class MemorySettings:
    """
    Настройки в памяти. Для тестов и headless-прогонов.

    Существует затем, чтобы проверять ядро с любыми значениями, не трогая
    файл пользователя. Раньше для этого приходилось подменять модуль целиком
    и надеяться, что подмена не переживёт тест: так однажды были переписаны
    настоящие настройки на машине разработчика.
    """

    def __init__(self, values=None):
        import threading

        from core.settings_store import defaults_for

        self._data = defaults_for()
        self._data.update(dict(values or {}))
        self._saved = 0
        self._lock = threading.RLock()

    def get(self, key, default=None):
        from core.settings_store import DEFAULTS

        return self._data.get(key, DEFAULTS.get(key, default))

    def set(self, key, value):
        self._data[key] = value

    def update(self, mapping):
        self._data.update(dict(mapping))

    def save(self):
        self._saved += 1
        return True

    @contextlib.contextmanager
    def transaction(self):
        with self._lock:
            yield self

    def all(self):
        return dict(self._data)

    @property
    def saves(self):
        """Сколько раз просили сохранить — полезно в тестах."""
        return self._saved


def default_settings():
    """Реализация по умолчанию — общее хранилище приложения."""
    from core.settings_store import settings

    return settings
