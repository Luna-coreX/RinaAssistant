"""
The interface for accessing the settings.

Plan item 4.0-B06. Before it, the core imported the module singleton
`core.settings_store.settings` and used it directly from a dozen places.
Three consequences, each of which gets in the way of the split:

    * two cores in one process are obliged to share one set of settings;
    * substituting other values in a test is possible only by replacing the
      module;
    * after the split the shell will not be able to get the settings over
      the protocol while "the settings" means "this particular file".

Described here is exactly what the core needs from the settings. The list is
deliberately short: everything not in it the core is not supposed to know —
neither where the file lies, nor what format it is in, nor how many groups
are there.

The default implementation is that same `settings_store`, so the behaviour
does not change. The point is not a new implementation but that the
dependency has become explicit.

There is no Qt here: the module lies in the core.
"""

import contextlib
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class SettingsProvider(Protocol):
    """The minimum the core needs."""

    def get(self, key: str, default: Any = None) -> Any:
        """A setting's value, or default."""
        ...

    def set(self, key: str, value: Any) -> None:
        """Write a value. Not necessarily to disk — see save()."""
        ...

    def save(self) -> bool:
        """Save what changed."""
        ...

    def transaction(self):
        """
        A lock over the whole read-change-write.

        Needed by the stores of history, reminders and statistics: the
        sequence "read the list — change it — write it" is not atomic in
        itself, and two threads lose each other's entries (see 3.1.0, R03).
        """
        ...


class MemorySettings:
    """
    Settings in memory. For tests and headless runs.

    It exists so that the core can be checked with any values without
    touching the user's file. This used to require replacing the whole
    module and hoping the replacement would not outlive the test: that is
    how a developer's real settings were once overwritten.
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
        """How many times a save was asked for — useful in tests."""
        return self._saved


def default_settings():
    """The default implementation — the application's shared store."""
    from core.settings_store import settings

    return settings
