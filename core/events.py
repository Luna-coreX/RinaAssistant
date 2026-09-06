"""
The core's event bus — with no dependency on Qt.

The assistant's core (recognition, commands, reminders) must not know about
the interface: otherwise it can neither be started separately from the
window nor shown in another shell. So the core only publishes events, and
who listens to them — a Qt adapter, a console or a process in another
language — is none of its business.

Subscribers are called in the same thread where the event happened. The core
works in background threads, so an interface adapter is obliged to carry
events into its own thread itself (in Qt a signal does that).
"""

import threading

from core.logging_setup import get_logger


log = get_logger("events")


class EventBus:
    def __init__(self):
        self._subs = {}
        self._lock = threading.RLock()

    def on(self, name, callback):
        """Subscribe to an event."""
        with self._lock:
            self._subs.setdefault(name, []).append(callback)
        return callback

    def off(self, name, callback):
        with self._lock:
            handlers = self._subs.get(name)
            if handlers and callback in handlers:
                handlers.remove(callback)

    def clear(self, name=None):
        with self._lock:
            if name is None:
                self._subs.clear()
            else:
                self._subs.pop(name, None)

    def emit(self, name, **payload):
        """
        Send an event. One subscriber's error must not get in the others'
        way and must not drop the core: an event is a notification, not a
        call.

        A subscriber takes the payload as **one dict**:
        `bus.on("speech.recognized", lambda data: ...)`.

        A swallowed error is always written to the journal. There used to be
        a silent `pass` here, and a subscriber with the wrong signature fell
        over on every event without leaving a trace: there simply were no
        events, and it looked like "the bus does not work". An error does
        not get in the others' way, but it must not be invisible.
        """
        with self._lock:
            handlers = list(self._subs.get(name, ()))
        for handler in handlers:
            try:
                handler(payload)
            except Exception:
                log.exception("Подписчик события %s упал", name)


# The application's single bus: the core needs a way to report events from
# any module without dragging a reference to the engine through every call.
bus = EventBus()
