"""
The user's commands.

A user creates commands through the editor on the "Commands" tab. Every
command is a dict:

    {
        "id": "cmd_ab12",
        "enabled": True,
        "type": "app" | "folder" | "website" | "speak" | "system" | "sequence",
        "triggers": ["запусти дискорд", "открой discord"],  # activation phrases
        "match": "contains" | "exact",                       # the match mode
        "target": "...",   # a path / url / text / action name (depends on the type)
        "response": "Хорошо, запускаю Discord",              # what to answer (optional)
        "steps": [ {subcommands} ],                          # for sequence only
    }

They are kept in the shared config (settings["custom_commands"]).
Execution is cross-platform: applications/folders/sites are opened by the
OS's standard means.
"""

import os
import sys
import uuid
import shutil
import subprocess
import webbrowser


COMMAND_TYPES = [
    ("app",      "Программа",        "🖥️"),
    ("folder",   "Папка",            "📁"),
    ("website",  "Сайт",             "🌐"),
    ("speak",    "Озвучить текст",   "🔊"),
    ("system",   "Системное действие", "⚙️"),
    ("sequence", "Последовательность", "🔗"),
]

# Actions on Rina's own window are performed by the main window (host);
# actions with the sys_ prefix by voice/system_control (volume, media, PC).
SYSTEM_ACTIONS = [
    ("minimize",             "Свернуть окно Рины"),
    ("show",                 "Показать окно Рины"),
    ("quit",                 "Выйти из Рины"),
    ("mute",                 "Отключить озвучку"),
    ("unmute",               "Включить озвучку"),
    ("sys_volume_up",        "Прибавить громкость"),
    ("sys_volume_down",      "Убавить громкость"),
    ("sys_volume_mute",      "Переключить звук системы"),
    ("sys_media_play_pause", "Пауза / продолжить"),
    ("sys_media_next",       "Следующий трек"),
    ("sys_media_prev",       "Предыдущий трек"),
    ("sys_screenshot",       "Сделать скриншот"),
    ("sys_lock",             "Заблокировать компьютер"),
    ("sys_sleep",            "Спящий режим"),
    ("sys_restart",          "Перезагрузить компьютер"),
    ("sys_shutdown",         "Выключить компьютер"),
]

# Actions that must not be performed without confirmation: a recognition
# error or an accidentally matching phrase must not shut the computer down.
DESTRUCTIVE_ACTIONS = {"sys_shutdown", "sys_restart", "sys_sleep", "quit"}


def action_label(action_id):
    for aid, label in SYSTEM_ACTIONS:
        if aid == action_id:
            return label
    return action_id


def command_needs_confirm(command):
    """Is there an irreversible action in the command (or in its steps)."""
    if command.get("type") == "system":
        return command.get("target") in DESTRUCTIVE_ACTIONS
    if command.get("type") == "sequence":
        return any(step.get("type") == "system"
                   and step.get("target") in DESTRUCTIVE_ACTIONS
                   for step in command.get("steps", []))
    return False


def new_command_id():
    return "cmd_" + uuid.uuid4().hex[:6]


def make_command(cmd_type="app", triggers=None, target="", response="",
                 match="contains", enabled=True, steps=None,
                 target_kind="file"):
    return {
        "id": new_command_id(),
        "enabled": bool(enabled),
        "type": cmd_type,
        "triggers": triggers or [],
        "match": match,
        "target": target,
        # what the target is: a file/path or a Store application's identifier
        "target_kind": target_kind,
        "response": response,
        "steps": steps or [],
    }


def type_label(cmd_type):
    for t, label, _ in COMMAND_TYPES:
        if t == cmd_type:
            return label
    return cmd_type


def type_icon(cmd_type):
    for t, _, icon in COMMAND_TYPES:
        if t == cmd_type:
            return icon
    return "•"


# ---------------------------------------------------------------------------
# The store
# ---------------------------------------------------------------------------
class UserCommandStore:
    def __init__(self, settings):
        self._settings = settings

    def all(self):
        return list(self._settings.get("custom_commands", []) or [])

    def save_all(self, commands):
        self._settings.set("custom_commands", commands)
        self._settings.save()

    def add(self, command):
        with self._settings.transaction():
            cmds = self.all()
            cmds.append(command)
            self.save_all(cmds)

    def update(self, command):
        with self._settings.transaction():
            cmds = self.all()
            for i, c in enumerate(cmds):
                if c.get("id") == command.get("id"):
                    cmds[i] = command
                    break
            self.save_all(cmds)

    def remove(self, command_id):
        with self._settings.transaction():
            cmds = [c for c in self.all() if c.get("id") != command_id]
            self.save_all(cmds)

    def set_enabled(self, command_id, enabled):
        with self._settings.transaction():
            cmds = self.all()
            for c in cmds:
                if c.get("id") == command_id:
                    c["enabled"] = bool(enabled)
            self.save_all(cmds)

    # launch statistics
    def bump_stat(self, command_id):
        with self._settings.transaction():
            stats = dict(self._settings.get("command_stats", {}) or {})
            stats[command_id] = stats.get(command_id, 0) + 1
            self._settings.set("command_stats", stats)
            self._settings.save()

    def stat(self, command_id):
        return (self._settings.get("command_stats", {}) or {}).get(command_id, 0)


# ---------------------------------------------------------------------------
# Matching and execution
# ---------------------------------------------------------------------------
def matches(command, text):
    """
    Does the command suit the recognised text.

    The comparison is fuzzy: speech recognition muddles endings and letters
    ("зопусти дискорт"), and an exact substring match loses such variants.
    The "Exact match" mode also allows for a recognition error, but requires
    the whole phrase to match rather than to be contained.
    """
    if not command.get("enabled", True):
        return False

    from voice.textmatch import similar, contains_phrase

    exact_mode = command.get("match") == "exact"
    for trig in command.get("triggers", []):
        trigger = str(trig).strip()
        if not trigger:
            continue
        if exact_mode:
            if similar(text, trigger):
                return True
        else:
            if contains_phrase(text, trigger):
                return True
    return False


def missing_path(target) -> bool:
    """
    The target looks like a path, but there is no such path.

    A command outlives a program: the path may be left over from a deleted
    or moved application. A short name ("discord") is not counted as a path
    — the OS itself resolves it through the App Paths registry, and that is
    a permissible way of setting a command.
    """
    target = str(target or "")
    if not target:
        return False
    looks_like_path = (os.path.isabs(target) or os.sep in target
                       or "/" in target)
    return looks_like_path and not os.path.exists(target)


def _open_path(path):
    """Open a file/folder/application in the OS's standard way."""
    if not path:
        return False
    if missing_path(path):
        return False
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)  # noqa
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            # if this is an executable in PATH — we launch it, otherwise xdg-open
            if shutil.which(path):
                subprocess.Popen([path])
            else:
                subprocess.Popen(["xdg-open", path])
        return True
    except Exception:
        return False


def execute(command, host=None, emit=None):
    """
    Performs a command. host is an object with methods for system actions
    (minimize/show/quit/mute/unmute) and say(text). Returns (ok,
    response_text).
    """
    from core.i18n import t as tr

    ctype = command.get("type")
    target = command.get("target", "")
    response = command.get("response", "")

    ok = True
    if ctype == "app" and command.get("target_kind") == "uwp":
        # a Store application: launched by identifier, not by path
        from voice import app_index
        ok = app_index.launch(
            app_index.AppEntry(target, target, "uwp", "learned"))
    elif ctype == "app" or ctype == "folder":
        if missing_path(target):
            # we name the reason: "it did not work" does not suggest what to do
            ok = False
            response = response or tr(
                "Не нашла «{target}» — программу удалили или перенесли.",
                target=os.path.basename(str(target).rstrip("\\/")) or target)
        else:
            ok = _open_path(target)
    elif ctype == "website":
        url = target
        if url and not url.startswith(("http://", "https://")):
            url = "https://" + url
        try:
            webbrowser.open(url)
        except Exception:
            ok = False
    elif ctype == "speak":
        # for "say the text out loud" the answer is the text itself (target),
        # if no separate response is set
        if not response:
            response = target
    elif ctype == "system":
        ok = _run_system_action(target, host, emit)
    elif ctype == "pause":
        # a pause between steps: to give the program time to start.
        # We limit it from above, so a typo does not hang execution for long.
        import time
        try:
            seconds = max(0.0, min(float(str(target).replace(",", ".")), 60.0))
        except (TypeError, ValueError):
            seconds = 1.0
        time.sleep(seconds)
        ok = True
    elif ctype == "sequence":
        ok = True
        for step in command.get("steps", []):
            step_ok, _ = execute(step, host, emit)
            ok = ok and step_ok
    else:
        ok = False

    if not response:
        # the default answer
        response = _default_response(command, ok)
    return ok, response


def _run_system_action(action, host, emit=None):
    # actions on the computer (volume, media, locking) — they need no host
    if str(action).startswith("sys_"):
        from voice import system_control
        from core.i18n import t as tr
        message = system_control.run(action[4:])
        # run() returns text on failure too — so we compare against exactly
        # that, or a step of a sequence would report "Done" after a failure
        return bool(message) and message != tr("Не получилось выполнить действие.")

    # actions on Rina's window touch widgets, and a command may run in a
    # background thread (speech recognition) — we take them into the GUI
    # thread with a signal
    mapping = {
        "minimize": "action_minimize",
        "show": "action_show",
        "quit": "action_quit",
        "mute": "action_mute",
        "unmute": "action_unmute",
    }
    if action not in mapping:
        return False
    # The event goes to the bus that was passed in rather than to the module
    # singleton: otherwise the action goes past the very core that started
    # it (4.0-B05).
    if emit is not None:
        from core.protocol import Events

        emit(Events.WINDOW_ACTION, action=action)
        return True
    # the fallback path, if no bus was passed in
    if host is not None and hasattr(host, mapping[action]):
        try:
            getattr(host, mapping[action])()
            return True
        except Exception:
            return False
    return False


def _default_response(command, ok):
    from core.i18n import t as tr

    ctype = command.get("type")
    if not ok:
        return tr("Не получилось выполнить команду.")
    if ctype == "app":
        return tr("Запускаю программу.")
    if ctype == "folder":
        return tr("Открываю папку.")
    if ctype == "website":
        return tr("Открываю сайт.")
    if ctype == "speak":
        return command.get("target", "")
    if ctype == "system":
        return tr("Готово.")
    if ctype == "sequence":
        return tr("Выполняю последовательность.")
    return tr("Готово.")
