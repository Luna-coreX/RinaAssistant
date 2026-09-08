"""
A small bus of application signals — so that pages can notify the main
window (and the other way round) without direct references to one another.
"""

from PySide6.QtCore import QObject, Signal


class _AppSignals(QObject):
    # the minimise-to-tray setting changed
    tray_pref_changed = Signal()

    # the user changed the hotkey -> re-register it
    hotkey_changed = Signal()

    # the window reports whether the global hotkey is available (bool) — for a hint in the UI
    hotkey_status = Signal(bool)

    # the "always listen" toggle on Rina's page changed
    always_listen_changed = Signal(bool)

    # the list of user commands changed (created/deleted/edited)
    commands_changed = Signal()

    # a request to run a user command by id (the "Run" button)
    run_command = Signal(str)

    # an entry was added to the history
    history_changed = Signal()

    # the interface language changed — rebuild the UI
    language_changed = Signal()

    # the program could not be launched — offer to point at the file by hand
    app_not_found = Signal(str)      # what was being looked for

    # the list of timers/reminders changed — refresh the tab
    reminders_changed = Signal()

    # an action on Rina's window (minimise/show/quit/speech).
    # A signal is exactly what is needed: commands run in the recognition
    # thread, and widgets may only be touched from the GUI thread.
    window_action = Signal(str)      # the action's id

    def __init__(self):
        super().__init__()
        self.last_hotkey_global = False  # a cache of the last status for the UI

    def _remember_status(self, ok):
        self.last_hotkey_global = ok


app_signals = _AppSignals()
app_signals.hotkey_status.connect(app_signals._remember_status)
