"""
Exporting and importing the user's data.

Commands are carried between computers, the history is exported for reading
outside the application. The format is JSON with a version and a kind:
without them an import will not tell a file of commands from a file of
history and will not survive a change of format.

Importing commands ADDS by default rather than replacing: substituting the
whole set of commands with one wrong click is too expensive a mistake.
"""

import json
import time

from version import APP_VERSION


FORMAT_VERSION = 1
KIND_COMMANDS = "rina.commands"
KIND_HISTORY = "rina.history"


class TransferError(Exception):
    """
    The file would not do: the wrong format, broken JSON, somebody else's
    data.

    Carries a protocol error code alongside the words. The shell branches on
    the code and shows the words: a person picking a history file where
    commands were asked for needs a sentence, and the shell needs something
    it can tell from "the file is unreadable" without matching on prose.
    """

    def __init__(self, message, code="transfer.unreadable"):
        super().__init__(message)
        self.code = code


def _envelope(kind, payload):
    return {
        "kind": kind,
        "format": FORMAT_VERSION,
        "app_version": APP_VERSION,
        "exported_at": time.time(),
        "payload": payload,
    }


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------
def export_commands(path, commands, stats=None):
    """Saves the commands (and the launch statistics) to a file."""
    data = _envelope(KIND_COMMANDS, {
        "commands": list(commands or []),
        "stats": dict(stats or {}),
    })
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return len(data["payload"]["commands"])


def commands_payload(commands, stats=None):
    """
    The content of a commands file — without writing it anywhere.

    Splitting this out of `export_commands` is what lets the protocol hand
    the file's content over the wire (§6: the shell picks the place and
    writes; the core hands over the content) and still produce **the same
    file** as 3.1.0. Two ways of assembling one format would part company,
    and the divergence would show up as "the export from the new version
    does not open in the old one".
    """
    return _envelope(KIND_COMMANDS, {
        "commands": list(commands or []),
        "stats": dict(stats or {}),
    })


def history_payload(entries):
    """The content of a history file. Same reasoning as `commands_payload`."""
    return _envelope(KIND_HISTORY, {"history": list(entries or [])})


def commands_from_data(data, source="файл"):
    """
    Parsed JSON -> commands fit to be added. Raises TransferError.

    Takes data rather than a path because the file is read by whoever has
    the file dialogue — in 4.0 that is the shell. What must not move with
    the file is the **judgement**: which kind this is, whether the format is
    ours, what may be let through. That is meaning, and meaning lives in the
    core.

    A command is the launching of a program, and this file could have been
    written by anyone. So everything that comes through here is brought to a
    safe shape and arrives switched off.
    """
    if isinstance(data, list):
        # A bare list is easy to get by hand, and refusing it would mean
        # refusing the obvious for the sake of tidiness.
        commands = data
    elif isinstance(data, dict):
        if "payload" not in data and isinstance(data.get("commands"), list):
            commands = data["commands"]
        else:
            if data.get("kind") != KIND_COMMANDS:
                raise TransferError("Это не файл команд", "transfer.wrong_kind")
            try:
                file_format = int(data.get("format", 0))
            except (TypeError, ValueError):
                raise TransferError("Не удалось прочитать версию формата файла",
                                    "transfer.unreadable")
            if file_format > FORMAT_VERSION:
                raise TransferError(
                    "Файл сделан более новой версией Рины — обновите приложение",
                    "transfer.too_new")
            commands = (data.get("payload") or {}).get("commands", [])
    else:
        raise TransferError("Файл не похож на экспорт Рины",
                            "transfer.unreadable")

    if not isinstance(commands, list):
        raise TransferError("В файле нет списка команд", "transfer.unreadable")
    if len(commands) > MAX_COMMANDS:
        raise TransferError(
            f"Слишком много команд в файле (больше {MAX_COMMANDS})",
            "transfer.unreadable")

    clean = [_sanitize_command(c) for c in commands
             if isinstance(c, dict) and c.get("triggers")]
    from core.logging_setup import security_log
    security_log().info(
        "Импорт команд из %s: в файле %d, принято %d, отброшено %d, "
        "все выключены", source, len(commands), len(clean),
        len(commands) - len(clean))
    return clean


def read_commands(path):
    """
    Reads a file of commands. Returns a list of commands.
    Raises TransferError if the file is the wrong one.
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        raise TransferError(f"Не удалось прочитать файл: {e}",
                            "transfer.unreadable")
    return commands_from_data(data, source=path)


# A file of commands could have been written by anyone, and a command is the
# launching of a program. So what is imported is brought to a safe form and
# arrives switched off: the user switches it on by hand, having seen what
# exactly they added.
MAX_COMMANDS = 500
MAX_TRIGGERS = 20
MAX_TRIGGER_LEN = 200
MIN_TRIGGER_LEN = 2


def _sanitize_command(raw):
    """Keeps only the known fields and brings them to the expected types."""
    from voice.user_commands import COMMAND_TYPES, SYSTEM_ACTIONS

    known_types = {t for t, _label, *_ in COMMAND_TYPES} | {"pause"}
    cmd_type = str(raw.get("type", "app"))
    if cmd_type not in known_types:
        cmd_type = "speak"          # an unknown kind launches nothing

    triggers = []
    for trigger in (raw.get("triggers") or [])[:MAX_TRIGGERS]:
        trigger = str(trigger).strip()[:MAX_TRIGGER_LEN]
        # too short a phrase would fire on almost any line
        if len(trigger) >= MIN_TRIGGER_LEN:
            triggers.append(trigger)

    target = str(raw.get("target", ""))[:1000]
    if cmd_type == "system":
        actions = {a for a, _ in SYSTEM_ACTIONS}
        if target not in actions:
            cmd_type, target = "speak", ""

    steps = raw.get("steps") or []
    steps = [_sanitize_command(s) for s in steps[:50] if isinstance(s, dict)]

    return {
        "id": str(raw.get("id", "")),
        # what is imported is always off: switching on is a deliberate step
        "enabled": False,
        "type": cmd_type,
        "triggers": triggers,
        "match": "exact" if raw.get("match") == "exact" else "contains",
        "target": target,
        "target_kind": "uwp" if raw.get("target_kind") == "uwp" else "file",
        "response": str(raw.get("response", ""))[:500],
        "steps": steps,
    }


def merge_commands(existing, incoming, new_id):
    """
    Adds the imported commands to the existing ones.

    A match is taken to be the same set of activation phrases: a file from
    another computer has ids of its own, while the phrases are what the
    command is to the user. Returns (the resulting list, added, duplicates
    skipped).
    """
    from voice.textmatch import normalize

    def key(cmd):
        return frozenset(normalize(t) for t in cmd.get("triggers", []) if t)

    result = list(existing or [])
    known = {key(c) for c in result}
    added = skipped = 0

    for cmd in incoming or []:
        cmd_key = key(cmd)
        if not cmd_key or cmd_key in known:
            skipped += 1
            continue
        copy = dict(cmd)
        copy["id"] = new_id()          # a foreign id could clash with a local one
        result.append(copy)
        known.add(cmd_key)
        added += 1
    return result, added, skipped


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------
def export_history_json(path, entries):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(_envelope(KIND_HISTORY, {"history": list(entries or [])}),
                  f, ensure_ascii=False, indent=2)
    return len(entries or [])


def export_history_text(path, entries):
    """A readable export: date, time, who, text."""
    lines = []
    last_day = None
    for entry in entries or []:
        stamp = time.localtime(entry.get("ts", 0))
        day = time.strftime("%d.%m.%Y", stamp)
        if day != last_day:
            lines.append("")
            lines.append(f"=== {day} ===")
            last_day = day
        who = "Вы" if entry.get("kind") == "user" else "Rina"
        lines.append(f"[{time.strftime('%H:%M', stamp)}] {who}: "
                     f"{entry.get('text', '')}")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines).strip() + "\n")
    return len(entries or [])
