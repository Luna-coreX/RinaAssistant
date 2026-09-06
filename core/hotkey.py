"""
The global hotkey.

The problem: QShortcut fires only when the window has focus. To summon Rina
from anywhere (even when the window is minimised to the tray), a system-wide
keyboard interception is needed. We use pynput (an optional dependency): it
listens to the keyboard in a background thread at the OS level.

Note: pynput's callback arrives from ANOTHER thread. Qt widgets must not be
touched from a foreign thread — so we forward the event into the GUI thread
through a Qt signal (HotkeyManager.activated), which the main window then
connects to.

If pynput is not installed, the application goes on working, simply without
a global hotkey (we show a hint in the UI). The combination is still
available while the window has focus, through the QShortcut the main window
hangs separately.
"""

import threading
import time

from PySide6.QtCore import QObject, Signal

try:
    from pynput import keyboard as _pynput_keyboard
    PYNPUT_AVAILABLE = True
except Exception:
    _pynput_keyboard = None
    PYNPUT_AVAILABLE = False


def qt_to_pynput_hotkey(sequence: str) -> str:
    """
    Converts a Qt-style string ("Ctrl+Shift+R") into pynput's format
    ("<ctrl>+<shift>+r"). Returns None if the parse failed.
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
            # function keys and the like: F5 -> <f5>, Space -> <space>
            out.append(f"<{low}>")

    # a hotkey without an ordinary key (modifiers only) makes no sense
    has_key = any(not p.startswith("<") or p[1:-1] not in
                  ("ctrl", "shift", "alt", "cmd") for p in out)
    if not has_key:
        return None

    return "+".join(out)


class HotkeyManager(QObject):
    """
    Registers global hotkeys and sends signals into the GUI thread.
    Supports the main hotkey (activated) and named actions
    (action_activated with the action's id).
    """

    activated = Signal()            # the main "listen" hotkey
    action_activated = Signal(str)  # an extra action by id

    # Holding the combination gives keyboard auto-repeat, and pynput
    # honestly reports every repeat. Without suppression one press ran the
    # command several times in a row.
    DEBOUNCE_SECONDS = 0.3

    def __init__(self, parent=None):
        super().__init__(parent)
        self._listener = None
        self._current = None
        self._action_map = {}       # action_id -> sequence
        self._last_fire = {}        # what fired last, and when
        self._fire_lock = threading.Lock()

    def _too_soon(self, key) -> bool:
        """A firing too close to the previous one for the same combination."""
        now = time.monotonic()
        with self._fire_lock:
            last = self._last_fire.get(key, 0.0)
            if now - last < self.DEBOUNCE_SECONDS:
                return True
            self._last_fire[key] = now
            return False

    @property
    def available(self) -> bool:
        return PYNPUT_AVAILABLE

    def register(self, sequence: str, actions: dict = None) -> bool:
        """
        Registers the main hotkey plus (optionally) a map of actions
        {action_id: "Ctrl+Alt+X"}. A repeat call replaces everything.
        Returns True if the main hotkey was registered.
        """
        self.unregister()
        self._action_map = dict(actions or {})
        with self._fire_lock:
            self._last_fire.clear()

        if not PYNPUT_AVAILABLE:
            return False

        hotkeys = {}
        main_ok = False

        combo = qt_to_pynput_hotkey(sequence)
        if combo:
            hotkeys[combo] = self._on_triggered
            main_ok = True
            self._current = sequence

        # the actions
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
            if self._too_soon(action_id):
                return
            self.action_activated.emit(action_id)
        return cb

    def _on_triggered(self):
        # called from pynput's thread -> we simply emit the signal (thread-safe)
        if self._too_soon("__main__"):
            return
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
