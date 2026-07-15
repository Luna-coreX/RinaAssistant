"""
Глобальная горячая клавиша.

Проблема: QShortcut срабатывает только когда окно в фокусе. Чтобы вызывать
Рину из любого места (даже когда окно свёрнуто в трей), нужен системный
перехват клавиатуры. Используем pynput (опциональная зависимость): он слушает
клавиатуру в фоновом потоке на уровне ОС.

Важно: колбэк pynput приходит из ДРУГОГО потока. Трогать Qt-виджеты из чужого
потока нельзя — поэтому пробрасываем событие в GUI-поток через сигнал Qt
(HotkeyManager.activated), к которому уже подключается главное окно.

Если pynput не установлен — приложение продолжает работать, просто без
глобального хоткея (в UI показываем подсказку). Комбинация при фокусе окна
всё равно доступна через QShortcut, который вешает главное окно отдельно.
"""

from PySide6.QtCore import QObject, Signal

try:
    from pynput import keyboard as _pynput_keyboard
    PYNPUT_AVAILABLE = True
except Exception:
    _pynput_keyboard = None
    PYNPUT_AVAILABLE = False


def qt_to_pynput_hotkey(sequence: str) -> str:
    """
    Преобразует строку в стиле Qt ("Ctrl+Shift+R") в формат pynput
    ("<ctrl>+<shift>+r"). Возвращает None, если распарсить не удалось.
    """
    if not sequence:
        return None

    parts = [p.strip() for p in sequence.split("+") if p.strip()]
    if not parts:
        return None

    mod_map = {
        "ctrl": "<ctrl>", "control": "<ctrl>",
        "shift": "<shift>",
        "alt": "<alt>", "option": "<alt>",
        "cmd": "<cmd>", "command": "<cmd>",
        "meta": "<cmd>", "super": "<cmd>", "win": "<cmd>",
    }

    out = []
    for part in parts:
        low = part.lower()
        if low in mod_map:
            out.append(mod_map[low])
        elif len(part) == 1:
            out.append(low)
        else:
            # функциональные клавиши и пр.: F5 -> <f5>, Space -> <space>
            out.append(f"<{low}>")

    # хоткей без обычной клавиши (только модификаторы) не имеет смысла
    has_key = any(not p.startswith("<") or p[1:-1] not in
                  ("ctrl", "shift", "alt", "cmd") for p in out)
    if not has_key:
        return None

    return "+".join(out)


class HotkeyManager(QObject):
    """
    Регистрирует глобальные хоткеи и шлёт сигналы в GUI-поток.
    Поддерживает основной хоткей (activated) и именованные действия
    (action_activated с id действия).
    """

    activated = Signal()            # основной хоткей «слушать»
    action_activated = Signal(str)  # доп. действие по id

    def __init__(self, parent=None):
        super().__init__(parent)
        self._listener = None
        self._current = None
        self._action_map = {}       # action_id -> sequence

    @property
    def available(self) -> bool:
        return PYNPUT_AVAILABLE

    def register(self, sequence: str, actions: dict = None) -> bool:
        """
        Регистрирует основной хоткей + (опционально) карту действий
        {action_id: "Ctrl+Alt+X"}. Повторный вызов заменяет всё.
        Возвращает True, если основной хоткей зарегистрирован.
        """
        self.unregister()
        self._action_map = dict(actions or {})

        if not PYNPUT_AVAILABLE:
            return False

        hotkeys = {}
        main_ok = False

        combo = qt_to_pynput_hotkey(sequence)
        if combo:
            hotkeys[combo] = self._on_triggered
            main_ok = True
            self._current = sequence

        # действия
        for action_id, seq in self._action_map.items():
            c = qt_to_pynput_hotkey(seq)
            if c and c not in hotkeys:
                hotkeys[c] = self._make_action_cb(action_id)

        if not hotkeys:
            return False

        try:
            self._listener = _pynput_keyboard.GlobalHotKeys(hotkeys)
            self._listener.daemon = True
            self._listener.start()
            return main_ok
        except Exception:
            self._listener = None
            self._current = None
            return False

    def _make_action_cb(self, action_id):
        def cb():
            self.action_activated.emit(action_id)
        return cb

    def _on_triggered(self):
        # вызывается из потока pynput -> просто эмитим сигнал (thread-safe)
        self.activated.emit()

    def unregister(self):
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception:
                pass
            self._listener = None
        self._current = None

    def current(self):
        return self._current
