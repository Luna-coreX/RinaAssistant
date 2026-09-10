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

from core.logging_setup import get_logger


log = get_logger("commands")


COMMAND_TYPES = [
    ("app",      "Программа",        "🖥️"),
    ("folder",   "Папка",            "📁"),
    ("website",  "Сайт",             "🌐"),
    ("speak",    "Озвучить текст",   "🔊"),
    ("system",   "Системное действие", "⚙️"),
    ("sequence", "Последовательность", "🔗"),
    # --- what a sequence is built out of (`4.0b-A09`) ------------------
    #
    # `pause` has been executable since 2.0.0 and was **never offered**:
    # the editor filled its list of kinds from the table above, and the
    # table did not have it. A capability nobody can reach is not a
    # capability; found by asking why a person could not put a wait
    # between "launch" and "maximise".
    ("pause",    "Подождать",        "⏳"),
    # Repetition and choice. These are control flow over **calls of
    # declared tools**, not a way to run something arbitrary: a step
    # inside them is an ordinary step and goes the same path with the
    # same gates. That is the line the plan draws, and it is not crossed
    # by letting a person say "three times" or "only in the evening".
    ("repeat",   "Повторить",        "🔁"),
    ("while",    "Повторять пока",   "🔄"),
    ("if",       "Если",             "🔀"),
    ("stop",     "Остановить сценарий", "⏹"),
    ("call",     "Вызвать команду",  "📎"),
    ("set",      "Запомнить значение", "🏷"),
]

#: What a condition can ask about.
#:
#: Deliberately short, and every one of them answerable **locally and
#: instantly**. A condition that has to go and look at something takes as
#: long as the thing it looks at, and a command that hangs on an unreachable
#: network share is worse than one that cannot ask about it at all.
CONDITIONS = [
    ("after",       "Сейчас позже, чем"),
    ("before",      "Сейчас раньше, чем"),
    ("weekday",     "Сегодня будний день"),
    ("weekend",     "Сегодня выходной"),
    ("date_is",     "Сегодня число"),
    ("exists",      "Файл или папка есть"),
    ("missing",     "Файла или папки нет"),
    # --- what is going on outside the command -------------------------
    #
    # These ask the machine, and the machine is the shell's (ADR 0009):
    # the core asks and is answered. Nothing is remembered — the answer is
    # used for the branch and dropped, the same rule as `4.0b-A03` and for
    # the same reason (`T-19`).
    ("app_active",  "Сейчас открыта программа"),
    ("app_running", "Программа запущена"),
    ("ollama",      "Ollama на связи"),
    # A variable set earlier in this same run.
    ("var_is",      "Значение равно"),
    ("var_set",     "Значение задано"),
]

#: Kinds that are steps of a sequence and not commands in their own right.
#:
#: A command of type "wait" would be a command that does nothing on purpose;
#: a command that is only a repeat or only a condition says nothing about
#: what it repeats or chooses between. All three are meaningful **inside** a
#: sequence and empty outside one.
#:
#: The core says this rather than the shell, because it is a statement about
#: what these things mean, not about how to show them (ADR 0006). A shell
#: deciding it for itself would be a second place where it is decided.
STEP_ONLY = frozenset({"pause", "repeat", "while", "if", "stop", "call",
                       "set"})

#: How many times a repeat may run, and how deep control flow may nest.
#:
#: Both are limits against a slip rather than against an attacker: "repeat
#: 1000 times" is almost always a typo, and a person who meant it can say
#: so twice. The nesting limit is what stops a card from being able to
#: describe an unbounded amount of work.
MAX_REPEAT = 50
MAX_DEPTH = 5

#: How many rounds "repeat while" may take before it is stopped.
#:
#: A condition that never stops holding is not a mistake anybody notices
#: while writing it — "while the file is missing" is perfectly sensible and
#: perfectly endless if the file never appears. The cap is what keeps a
#: scenario a scenario rather than a way to occupy the machine forever.
MAX_WHILE = 200

#: How long a variable's name and value may be. They are written by the
#: person, kept for the length of one run, and never stored.
MAX_NAME = 64
MAX_VALUE = 1000


class ScenarioStopped(Exception):
    """
    A step asked for the whole scenario to stop.

    An exception rather than a return value, because stopping has to unwind
    through the repeats and branches it happens to be inside. Threading a
    "and now stop" flag back out through every one of them would mean every
    caller remembering to look at it, and the one that forgot would keep
    going after the person said to stop.
    """

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
        """
        Write the list as a whole.

        Under a transaction, like everything else here: the neighbouring
        methods open one and this one did not. The lock is reentrant, so a
        nested call from inside somebody else's transaction works as
        before.

        **This alone is not enough, and it is worth saying why.** The lock
        makes the write indivisible but not the read-modify-write: two
        threads that read the same list will each append their own, and the
        second will overwrite the first entirely. That is what `merge` is
        for.
        """
        with self._settings.transaction():
            self._settings.set("custom_commands", commands)
            self._settings.save()

    def merge(self, incoming, new_id):
        """
        Add the incoming commands to our own. Returns (added, skipped).

        Reading, merging and writing under one transaction. Apart they lose
        somebody else's edit entirely: an import from a file and an answer
        from Rina run on different threads, both read the list, both append
        their own, and whoever got there second is the one who saves.

        The merging lives here rather than in the caller for exactly that
        reason: a transaction's boundaries must coincide with the
        boundaries of read-modify-write, and the caller is not obliged to
        remember it.
        """
        from core.data_transfer import merge_commands

        with self._settings.transaction():
            merged, added, skipped = merge_commands(
                self.all(), incoming, new_id)
            self.save_all(merged)
        return added, skipped

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


def _fresh_state(lookup=None, machine=None):
    """
    What a scenario carries with it for the length of one run.

    Variables live here and nowhere else. They are **not** stored: a value a
    person set in the middle of a scenario is working notes, and keeping it
    on disk would turn "remember 5" into a new kind of personal data with a
    page, a lifetime and a way to forget it. When the run ends, it is gone.

    `seen` is the guard against a command that calls itself, directly or
    round a ring. `lookup` finds another command by its number; `machine`
    answers the questions that are about the computer rather than about the
    card, and both are handed in because neither belongs to this module.
    """
    return {"vars": {}, "seen": set(), "lookup": lookup, "machine": machine}


def _run_steps(steps, host, emit, depth, state):
    """
    Perform a list of steps in order, one level deeper.

    The depth is carried rather than counted globally: two sequences side by
    side are not nesting, and a limit that thought they were would refuse
    perfectly ordinary commands. Past the limit the steps are simply not
    run — a card that describes an unbounded amount of work does not get to
    do an unbounded amount of work.
    """
    if depth >= MAX_DEPTH:
        log.warning("Слишком глубокая вложенность шагов, дальше не идём")
        return False
    ok = True
    for step in steps or []:
        step_ok, _ = execute(step, host, emit, depth + 1, state)
        ok = ok and step_ok
    return ok


def _call_command(command, host, emit, depth, state):
    """
    Run another command of the person's own, by its number.

    **A command may not call itself, directly or round a ring.**

    The depth limit already bounds this — depth is carried down through a
    call, so a ring runs out of depth like anything else. Said exactly,
    because the first version of this comment claimed the opposite ("two
    commands calling each other stay at depth one apiece"), and the check
    written from it passed with the guard below removed: it was watching
    the depth limit work and crediting the guard.

    The guard is still here and still worth having. It stops a ring **at
    the first repeat** instead of five levels down, which is the difference
    between one refused call and five performed ones on the way; and it
    says so in the log, where "too deep" would have sent somebody looking
    for deep nesting they never wrote.
    """
    lookup = state.get("lookup")
    wanted = str(command.get("target", ""))
    if lookup is None or not wanted:
        return False

    if wanted in state["seen"]:
        log.warning("Команда %s уже выполняется — по кругу не пойдём", wanted)
        return False

    other = None
    try:
        other = lookup(wanted)
    except Exception:
        log.exception("Не удалось найти команду %s", wanted)
    if not other:
        return False

    state["seen"].add(wanted)
    try:
        ok, _ = execute(other, host, emit, depth + 1, state)
        return ok
    finally:
        # Removed on the way out: calling the same command twice **in
        # sequence** is perfectly ordinary, and only calling it while it is
        # already running is a ring.
        state["seen"].discard(wanted)


def _ask_machine(state, question, about=""):
    """
    A question about the computer, asked of whoever has one.

    The core has no system calls of its own (ADR 0009). Without a shell the
    answer is empty rather than a guess: a condition that cannot be
    established is false, and a command that branched on a guess would do
    the wrong half of itself in silence.
    """
    ask = (state or {}).get("machine")
    if ask is None:
        return ""
    try:
        return ask(question, about) or ""
    except Exception:
        log.exception("Не удалось спросить у оболочки: %s", question)
        return ""


def _condition_holds(kind, value, name="", state=None):
    """
    Whether a condition is met, answered here and now.

    Two kinds of question live here. Ones about the card and the clock are
    answered outright. Ones about the machine — which program is in front,
    whether something is running — are asked of the shell and the answer is
    **dropped**: it decides a branch and is not kept, the same rule as
    `4.0b-A03` and for the same reason (`T-19`). Knowing what somebody has
    open is information of the same kind as the words they said.

    Everything is answered quickly or not at all. A condition that has to go
    and look at something slow takes as long as the thing it looks at, and a
    command hanging on an unreachable share is worse than one that cannot
    ask about it.
    """
    import datetime

    now = datetime.datetime.now()
    text = str(value or "")

    if kind in ("after", "before"):
        try:
            hour, _, minute = text.partition(":")
            when = now.replace(hour=int(hour), minute=int(minute or 0),
                               second=0, microsecond=0)
        except (TypeError, ValueError):
            # An unreadable time is not a reason to guess. "Later than
            # nonsense" is false, and the branch simply does not run.
            return False
        return now >= when if kind == "after" else now < when
    if kind == "weekday":
        return now.weekday() < 5
    if kind == "weekend":
        return now.weekday() >= 5
    if kind == "date_is":
        # "The 1st" — the day of the month, for things done monthly.
        try:
            return now.day == int(text)
        except (TypeError, ValueError):
            return False
    if kind in ("exists", "missing"):
        there = bool(text) and os.path.exists(text)
        return there if kind == "exists" else not there

    if kind == "app_active":
        front = _ask_machine(state, "foreground")
        return bool(text) and text.lower() in str(front).lower()
    if kind == "app_running":
        return bool(text) and bool(_ask_machine(state, "running", text))
    if kind == "ollama":
        from core import llm

        try:
            return bool(llm.status()[0])
        except Exception:
            return False

    if kind == "var_is":
        return str((state or {}).get("vars", {}).get(name, "")) == text
    if kind == "var_set":
        return bool(str((state or {}).get("vars", {}).get(name, "")))

    # An unknown condition — from a newer version's file, or a typo — is
    # false. Said exactly, because "false" is not the same as "nothing
    # happens": the "otherwise" branch is what a person wrote for the case
    # when the condition does not hold, and running it is the least
    # surprising reading. What must not happen is the *then* branch running
    # on a condition nobody could evaluate.
    return False


def execute(command, host=None, emit=None, depth=0, state=None,
            lookup=None, machine=None):
    """
    Performs a command. host is an object with methods for system actions
    (minimize/show/quit/mute/unmute) and say(text). Returns (ok,
    response_text).

    `state` carries what one run of a scenario needs — its variables, which
    commands it is already inside, and the two things it can ask of the
    outside. It is made here when there is none, so an ordinary call needs
    to know nothing about any of it.
    """
    from core.i18n import t as tr

    outermost = state is None
    if outermost:
        state = _fresh_state(lookup, machine)

    # The stop signal is caught **here**, at the outermost call, and
    # nowhere else. Caught deeper it would stop a branch rather than the
    # scenario, which is not what "stop the scenario" says.
    if outermost:
        try:
            return _perform(command, host, emit, depth, state)
        except ScenarioStopped:
            log.info("Сценарий остановлен шагом «остановить»")
            return True, command.get("response", "") or _default_response(
                command, True)
    return _perform(command, host, emit, depth, state)


def _perform(command, host, emit, depth, state):
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
        ok = _run_steps(command.get("steps", []), host, emit, depth, state)
    elif ctype == "stop":
        # Nothing after this runs, at any depth. See `ScenarioStopped`.
        raise ScenarioStopped()
    elif ctype == "set":
        # Working notes for the length of the run. Trimmed, because a
        # name or a value of any size at all would be a way to fill memory
        # from a card.
        # The name in `name`, what to remember in `value` — the same two
        # fields the conditions about a variable read. `target` is taken as
        # a fallback so a card written before this settled still works.
        name = str(command.get("name", ""))[:MAX_NAME].strip()
        what = command.get("value") or target
        if name:
            state["vars"][name] = str(what)[:MAX_VALUE]
        ok = bool(name)
    elif ctype == "call":
        ok = _call_command(command, host, emit, depth, state)
    elif ctype == "while":
        # A condition that never stops holding is not a mistake anybody
        # notices while writing it: "while the file is missing" is
        # sensible and endless if the file never appears.
        ok = True
        rounds = 0
        # `value`, not `target`: a condition's operand lives in `value`
        # for `if` and must live in the same place here. It read `target`
        # at first — always empty on a `while` — so the loop never began
        # and both its checks reported zero rounds.
        while _condition_holds(command.get("condition", ""),
                               command.get("value", ""),
                               command.get("name", ""), state):
            if rounds >= MAX_WHILE:
                log.warning("«Повторять пока» дошло до предела в %d кругов",
                            MAX_WHILE)
                ok = False
                break
            rounds += 1
            if not _run_steps(command.get("steps", []), host, emit, depth,
                              state):
                ok = False
                break
    elif ctype == "repeat":
        # "Three times" rather than three copies of the same step. The count
        # is capped: "repeat 1000 times" is almost always a slip, and a
        # person who meant it can say it twice.
        try:
            times = int(command.get("count", 1) or 1)
        except (TypeError, ValueError):
            times = 1
        times = max(0, min(times, MAX_REPEAT))
        ok = True
        for _ in range(times):
            if not _run_steps(command.get("steps", []), host, emit, depth,
                              state):
                # A repeat stops at the first failure rather than trying
                # again four more times. Whatever went wrong is unlikely to
                # go right on its own, and repeating a failing action is the
                # one thing nobody wants a computer to be enthusiastic about.
                ok = False
                break
    elif ctype == "if":
        met = _condition_holds(command.get("condition", ""),
                               command.get("value", ""),
                               command.get("name", ""), state)
        branch = "steps" if met else "otherwise"
        ok = _run_steps(command.get(branch) or [], host, emit, depth, state)
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
