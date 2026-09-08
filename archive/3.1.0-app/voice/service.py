"""
A Qt adapter over the assistant's core.

All the logic lives in core/engine.py and knows nothing about the interface.
Here it is turned into the familiar Qt signals: the core's events arrive
from background threads, and widgets may only be touched from the interface
thread — a signal is exactly what does that carrying.

The public interface is preserved in full (process_command, listen_once,
say, set_always_listen...), so the window and the pages work unchanged.
"""

from PySide6.QtCore import QObject, Signal

from core.engine import RinaEngine
from core.events import EventBus
from core.protocol import Events


class VoiceService(QObject):
    # the signals stayed the same as before the core was separated out
    listening_started = Signal()
    listening_stopped = Signal()
    recognized = Signal(str)
    responded = Signal(str)
    error = Signal(str)
    always_listen_changed = Signal(bool)
    always_capturing = Signal(bool)
    reminder_fired = Signal(dict)
    thinking = Signal(bool)           # the model is thinking about an answer

    def __init__(self, plugin_manager=None, parent=None):
        super().__init__(parent)
        # A bus of its own rather than the module singleton: the service
        # owns its core, and two instances must not hear each other's events
        # (4.0-B05).
        self.engine = RinaEngine(plugin_manager=plugin_manager,
                                 event_bus=EventBus())
        self._subscriptions = []
        self._connect_engine()
        self.engine.start_reminders()

    # ---------- the bridge between the core's bus and Qt's signals ----------
    def _connect_engine(self):
        # We subscribe to OUR core's bus, not to the module singleton. It
        # used to coincide only because the core takes that same object by
        # default; with a second core the events would go past (4.0-B05).
        engine_bus = self.engine.bus

        def bind(event_name, handler):
            self._subscriptions.append((event_name, handler))
            engine_bus.on(event_name, handler)

        bind(Events.LISTENING_STARTED, lambda d: self.listening_started.emit())
        bind(Events.LISTENING_STOPPED, lambda d: self.listening_stopped.emit())
        bind(Events.CAPTURING,
             lambda d: self.always_capturing.emit(bool(d.get("active"))))
        bind(Events.ALWAYS_LISTEN,
             lambda d: self.always_listen_changed.emit(bool(d.get("enabled"))))
        bind(Events.RECOGNIZED,
             lambda d: self.recognized.emit(str(d.get("text", ""))))
        bind(Events.RESPONSE,
             lambda d: self.responded.emit(str(d.get("text", ""))))
        bind(Events.ERROR,
             lambda d: self.error.emit(str(d.get("text", ""))))
        bind(Events.REMINDER_FIRED,
             lambda d: self.reminder_fired.emit(dict(d.get("item") or {})))
        bind(Events.THINKING,
             lambda d: self.thinking.emit(bool(d.get("active"))))

        # events the core addresses to the application as a whole
        bind(Events.HISTORY_CHANGED, lambda d: self._forward_history())
        bind(Events.APP_NOT_FOUND,
             lambda d: self._forward_app_not_found(str(d.get("query", ""))))
        bind(Events.WINDOW_ACTION,
             lambda d: self._forward_window_action(str(d.get("action", ""))))

    def _forward_history(self):
        from core.app_signals import app_signals
        app_signals.history_changed.emit()

    def _forward_app_not_found(self, query):
        from core.app_signals import app_signals
        app_signals.app_not_found.emit(query)

    def _forward_window_action(self, action):
        from core.app_signals import app_signals
        app_signals.window_action.emit(action)

    # ---------- the same API as before ----------
    def set_host(self, host):
        self.engine.set_host(host)

    def say(self, text, sound="response"):
        self.engine.say(text, sound=sound)

    def listen_once(self):
        self.engine.listen_once()

    def process_command(self, text, require_wake=False, source="typed"):
        # in the background: it is called from the interface thread, and the
        # pipeline may go to the network or to the language model for
        # several seconds
        self.engine.handle_command_async(
            text, require_wake=require_wake, source=source)

    def set_always_listen(self, on):
        self.engine.set_always_listen(on)

    def is_always_listen(self):
        return self.engine.is_always_listen()

    def run_command_by_id(self, command_id):
        self.engine.run_command_by_id(command_id)

    def shutdown(self):
        self.engine.shutdown()
        for event_name, handler in self._subscriptions:
            self.engine.bus.off(event_name, handler)
        self._subscriptions.clear()

    # ---------- the core's state ----------
    @property
    def _pending(self):
        """The unclosed clarifying question (used in tests and debugging)."""
        return self.engine._pending

    @_pending.setter
    def _pending(self, value):
        self.engine._pending = value
