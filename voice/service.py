"""
Qt-адаптер над ядром ассистента.

Вся логика живёт в core/engine.py и не знает про интерфейс. Здесь она
превращается в привычные сигналы Qt: события ядра приходят из фоновых
потоков, а трогать виджеты можно только из потока интерфейса — сигнал как
раз и делает этот перенос.

Публичный интерфейс сохранён полностью (process_command, listen_once, say,
set_always_listen…), поэтому окно и страницы работают без изменений.
"""

from PySide6.QtCore import QObject, Signal

from core.engine import RinaEngine
from core.events import bus
from core.protocol import Events


class VoiceService(QObject):
    # сигналы остались теми же, что и до выделения ядра
    listening_started = Signal()
    listening_stopped = Signal()
    recognized = Signal(str)
    responded = Signal(str)
    error = Signal(str)
    always_listen_changed = Signal(bool)
    always_capturing = Signal(bool)
    reminder_fired = Signal(dict)
    thinking = Signal(bool)           # модель обдумывает ответ

    def __init__(self, plugin_manager=None, parent=None):
        super().__init__(parent)
        self.engine = RinaEngine(plugin_manager=plugin_manager, event_bus=bus)
        self._subscriptions = []
        self._connect_engine()
        self.engine.start_reminders()

    # ---------- мост между шиной ядра и сигналами Qt ----------
    def _connect_engine(self):
        def bind(event_name, handler):
            self._subscriptions.append((event_name, handler))
            bus.on(event_name, handler)

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

        # события, которые ядро адресует приложению целиком
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

    # ---------- то же API, что и раньше ----------
    def set_host(self, host):
        self.engine.set_host(host)

    def say(self, text, sound="response"):
        self.engine.say(text, sound=sound)

    def listen_once(self):
        self.engine.listen_once()

    def process_command(self, text, require_wake=False, source="typed"):
        self.engine.handle_command(text, require_wake=require_wake, source=source)

    def set_always_listen(self, on):
        self.engine.set_always_listen(on)

    def is_always_listen(self):
        return self.engine.is_always_listen()

    def run_command_by_id(self, command_id):
        self.engine.run_command_by_id(command_id)

    def shutdown(self):
        self.engine.shutdown()
        for event_name, handler in self._subscriptions:
            bus.off(event_name, handler)
        self._subscriptions.clear()

    # ---------- состояние ядра ----------
    @property
    def _pending(self):
        """Незакрытый уточняющий вопрос (используется в тестах и отладке)."""
        return self.engine._pending

    @_pending.setter
    def _pending(self, value):
        self.engine._pending = value
