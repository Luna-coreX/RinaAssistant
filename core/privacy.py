"""
What Rina keeps about a person (`4.0b-B01`).

One inventory of everything stored locally, assembled from the store rather
than from a list written by hand. That distinction is the whole point of the
module.

**A privacy page that can go quietly out of date is worse than none.** If
the groups below were an enumeration somebody maintained, then the day a new
kind of personal data started being kept, the page would go on answering
"this is everything" — and it would be a lie told with a straight face by
the one screen a person opens in order to be told the truth. So the keys are
walked, not listed: anything in the store that no group here claims becomes a
group of its own, shown raw, under its own key. Ugly, and visible; and what
is ugly gets fixed.

**Names are not here.** The core says what it keeps and hands over the
entries; what the groups are *called* belongs to the shell (`4.0-F08`,
ADR 0006 — the core owns meaning, the shell owns presentation). The shell
also has to show a group it does not recognise, for the same reason the
settings page shows a key it does not recognise.
"""
import os
import shutil
import time

from core import settings_schema
from core.i18n import t as tr


class Local:
    """
    What is kept beside the settings, and who can reach it.

    **The page walked the store and nothing else** (audit 2026-10-07, H-4):
    the journals, the call journal, the copies made before a migration and
    what the shell keeps were all on the disk and none of them on the
    page, and «забыть всё» left a copy of the conversation in `backup-v*`
    and a year of launched programs in `security.log`. Whatever is not a
    key of the store reaches the page through this.

    `audit` and `telemetry` are the engine's own objects, not new ones: a
    second `Telemetry` forgot its own copy while the engine's wrote the old
    one straight back on the next command (M-1). `shell` asks the shell —
    `(method, payload) -> dict` — or is `None` when there is none.
    """

    def __init__(self, folder=None, audit=None, telemetry=None, shell=None):
        self.folder = folder
        self.audit = audit
        self.telemetry = telemetry
        self.shell = shell


def _text(value, limit=300):
    return str(value)[:limit]


def _aliases(settings):
    """Programs Rina has learned to call by a person's own words."""
    out = []
    for word, about in (settings.get("app_aliases", {}) or {}).items():
        if isinstance(about, dict):
            path = about.get("path", "")
            name = about.get("name", "")
        else:
            path, name = str(about), ""
        out.append({
            "id": _text(word, 200),
            "what": _text(word, 200),
            "detail": _text(name or os.path.basename(str(path)) or path),
            "where": _text(path),
            "when": 0.0,
        })
    return out


def _history(settings):
    out = []
    for at, entry in enumerate(settings.get("history", []) or []):
        if not isinstance(entry, dict):
            continue
        try:
            when = float(entry.get("ts", 0) or 0)
        except (TypeError, ValueError):
            when = 0.0
        out.append({
            # By position: an entry of the journal has no identifier of its
            # own, and inventing one here would mean inventing one that the
            # store does not know either.
            "id": str(at),
            "what": _text(entry.get("text", "")),
            "detail": _text(entry.get("kind", "")),
            "where": _text(entry.get("source", "")),
            "when": when,
        })
    return out


def _reminders(settings):
    out = []
    for entry in (settings.get("reminders", []) or []):
        if not isinstance(entry, dict):
            continue
        try:
            when = float(entry.get("when", 0) or 0)
        except (TypeError, ValueError):
            when = 0.0
        out.append({
            "id": _text(entry.get("id", ""), 100),
            "what": _text(entry.get("text", "")),
            "detail": _text(entry.get("kind", "")),
            "where": _text(entry.get("app", "")),
            "when": when,
        })
    return out


def _todo(settings):
    out = []
    for entry in (settings.get("todo", []) or []):
        if not isinstance(entry, dict):
            continue
        try:
            when = float(entry.get("created", 0) or 0)
        except (TypeError, ValueError):
            when = 0.0
        out.append({
            "id": _text(entry.get("id", ""), 100),
            "what": _text(entry.get("text", "")),
            "detail": "done" if entry.get("done") else "open",
            "where": "",
            "when": when,
        })
    return out


def _sessions(settings):
    """
    Working sessions (`4.0b-A02`), and the widest record here.

    A session holds what somebody was at, for how long, which
    applications were in front of them and — when they agreed to it —
    which folders they worked in. That is closer to a diary than
    anything else Rina keeps, which is exactly why it is spelled out
    row by row rather than summed up as "sessions: 12": a person
    looking at this page has to be able to see the day they want
    forgotten and forget it.
    """
    out = []
    for entry in (settings.get("sessions", []) or []):
        if not isinstance(entry, dict):
            continue
        try:
            when = float(entry.get("started", 0) or 0)
        except (TypeError, ValueError):
            when = 0.0
        apps = entry.get("apps", {})
        parts = []
        if entry.get("notes"):
            parts.append(tr("заметок {n}", n=len(entry["notes"])))
        if entry.get("commands"):
            parts.append(tr("команд {n}", n=len(entry["commands"])))
        if isinstance(apps, dict) and apps:
            parts.append(tr("приложений {n}", n=len(apps)))
        out.append({
            "id": _text(entry.get("id", ""), 100),
            "what": _text(entry.get("goal", "")),
            "detail": ", ".join(parts) or (tr("идёт") if not
                                           entry.get("finished")
                                           else tr("закрыта")),
            # The folders are the sharpest part of a session, so they
            # stand in the column that names a place rather than being
            # counted among the rest.
            "where": _text("; ".join(entry.get("folders") or []), 300),
            "when": when,
        })
    return out


def _commands(settings):
    out = []
    for entry in (settings.get("custom_commands", []) or []):
        if not isinstance(entry, dict):
            continue
        triggers = [str(t) for t in (entry.get("triggers") or [])]
        out.append({
            "id": _text(entry.get("id", ""), 100),
            "what": _text(", ".join(triggers)) or _text(entry.get("target", "")),
            "detail": _text(entry.get("type", "")),
            "where": _text(entry.get("target", "")),
            "when": 0.0,
        })
    return out


def _stats(settings):
    """How often each command has been run — a record of habits."""
    named = {}
    for entry in (settings.get("custom_commands", []) or []):
        if isinstance(entry, dict) and entry.get("id"):
            triggers = [str(t) for t in (entry.get("triggers") or [])]
            named[str(entry["id"])] = ", ".join(triggers)

    out = []
    for key, value in (settings.get("command_stats", {}) or {}).items():
        count = value.get("count") if isinstance(value, dict) else value
        last = value.get("last") if isinstance(value, dict) else 0
        try:
            when = float(last or 0)
        except (TypeError, ValueError):
            when = 0.0
        out.append({
            "id": _text(key, 100),
            "what": named.get(str(key)) or _text(key, 100),
            "detail": str(count),
            "where": "",
            "when": when,
        })
    return out


def _plugins(settings):
    """Which plugins are switched on and what they have kept."""
    out = []
    for name in (settings.get("enabled_plugins", []) or []):
        out.append({
            "id": _text(str(name), 100),
            "what": _text(str(name), 100),
            "detail": "",
            "where": "",
            "when": 0.0,
        })
    for name, kept in (settings.get("plugin_settings", {}) or {}).items():
        # **How many, not what.** A plugin's settings are a place for
        # anything at all, an access token included, and this page is meant
        # to be read over a shoulder: "the plugin keeps four things" answers
        # the question a person came with, while printing the four would
        # turn the privacy page into the one screen worth photographing.
        # What exactly a plugin keeps belongs on that plugin's own page,
        # where it was put in.
        size = len(kept) if isinstance(kept, dict) else 1
        out.append({
            "id": _text(str(name), 100),
            "what": _text(str(name), 100),
            "detail": str(size),
            "where": "",
            "when": 0.0,
        })
    return out


def _folders(settings):
    """Places on the disk a person told Rina to look in."""
    return [{
        "id": _text(str(path)),
        "what": _text(str(path)),
        "detail": "",
        "where": _text(str(path)),
        "when": 0.0,
    } for path in (settings.get("program_folders", []) or [])]


def _telemetry(settings, telemetry=None):
    """
    The beta's telemetry: what is gathered now, and every report that left.

    Shown whole, in the form the server received it — not summarised. A
    person who switched it on is owed the exact thing that went, and a
    summary would be this page's word against the wire's (`4.0b-D05`).
    """
    import json

    from core.telemetry import Telemetry

    # The engine's, when there is one: what is gathered lives in its memory
    # until it is written, and the file alone showed less (L-2).
    telemetry = telemetry or Telemetry(settings)
    out = []
    pending = telemetry.report()
    if pending is not None:
        out.append({
            "id": "pending",
            "what": tr("Накоплено, ещё не ушло"),
            "detail": json.dumps(pending, ensure_ascii=False),
            "where": "",
            "when": 0.0,
        })
    for one in telemetry.sent():
        out.append({
            "id": str(one.get("at", "")),
            "what": tr("Ушло на сервер"),
            "detail": json.dumps(one.get("report", {}), ensure_ascii=False),
            "where": "",
            "when": float(one.get("at") or 0.0),
        })
    return out


#: A group of the inventory: which keys of the store it accounts for, and
#: how to read them out. The key list is what makes the walk below able to
#: tell an accounted-for key from a new one.
GROUPS = (
    ("aliases", ("app_aliases",), _aliases),
    ("history", ("history",), _history),
    ("reminders", ("reminders",), _reminders),
    ("todo", ("todo",), _todo),
    ("sessions", ("sessions",), _sessions),
    ("commands", ("custom_commands",), _commands),
    ("stats", ("command_stats",), _stats),
    ("plugins", ("enabled_plugins", "plugin_settings"), _plugins),
    ("folders", ("program_folders",), _folders),
    ("telemetry", ("telemetry",), _telemetry),
)


def _changed_settings(settings):
    """
    Settings a person has changed from the default.

    Preferences are part of the answer to "what does this program know about
    me" — that the wake word is a particular name, that the voice is a
    particular voice. Only what was **changed**: a default nobody chose says
    nothing about anybody, and forty rows of them would bury the eight that
    do.
    """
    spoken_for = {key for _id, keys, _read in GROUPS for key in keys}
    schema = settings_schema.describe(sorted(settings_schema.SETTABLE))
    out = []
    for key in sorted(settings_schema.SETTABLE):
        if key in spoken_for:
            continue
        # The store's own state is not a preference and is not about
        # anybody: `config_version` and `first_run` say which shape the
        # file is in and whether the wizard has run. The schema already
        # marks them `secret` and `settings.get` already withholds them —
        # taking that rule from there rather than writing a second list
        # that would part company with it.
        #
        # **This was a real fault, not tidiness.** The export showed
        # "изменённые настройки: config_version = 2", and «забыть всё»
        # would have reset it to 0 — telling the store on next load that it
        # was two migrations behind. Found by reading the exported file.
        if schema.get(key, {}).get("secret"):
            continue
        # Obsolete keys stay. `theme` and `wake_word` were replaced, but
        # what a person chose is still written on their disk, and this is
        # the page that promises to say what is written there.
        default = settings_schema.DEFAULTS.get(key)
        value = settings.get(key, default)
        if value == default:
            continue
        out.append({
            "id": key,
            "what": key,
            "detail": _text(value, 200),
            "where": "",
            "when": 0.0,
        })
    return out


def _size(bytes_):
    for unit, step in (("ГБ", 1 << 30), ("МБ", 1 << 20), ("КБ", 1 << 10)):
        if bytes_ >= step:
            return f"{bytes_ / step:.1f} {unit}"
    return f"{bytes_} Б"


def _tree_size(path):
    total = 0
    for top, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(top, name))
            except OSError:
                pass
    return total


def _journals(local):
    """
    The journals: the core's, the security journal, the shell's.

    By file, with size and the last write: what is in them is events — and
    the security journal holds every program launched, with its path and
    time, and the settings changed (M-9). Named here so the page stops
    saying "this is everything" over a year of that.
    """
    from core.logging_setup import journals, logs_dir

    folder = logs_dir()
    items = []
    for name in journals():
        path = os.path.join(folder, name)
        try:
            items.append({"id": name, "what": name,
                          "detail": _size(os.path.getsize(path)),
                          "where": folder, "when": os.path.getmtime(path)})
        except OSError:
            continue
    return items


def _calls(local):
    """The call journal (`core/audit.py`): thirty days of what was done."""
    if local is None or local.audit is None:
        return None
    try:
        count = local.audit.count()
    except Exception:                                   # noqa: BLE001
        return None
    if not count:
        return []
    return [{"id": "all", "what": tr("Вызовов за последние 30 дней: {n}",
                                     n=count),
             "detail": "", "where": getattr(local.audit, "path", "") or "",
             "when": 0.0}]


def _backups(local):
    """
    Copies the store made of itself before a migration (`backup-v*`) and
    any other `backup-*` beside it.

    Whole copies of the history, the commands, the reminders as they were
    then — the one place «забыть всё» left a conversation behind.
    """
    if local is None or not local.folder:
        return None
    items = []
    try:
        names = sorted(os.listdir(local.folder))
    except OSError:
        return []
    for name in names:
        path = os.path.join(local.folder, name)
        if not (name.startswith("backup-") and os.path.isdir(path)):
            continue
        items.append({"id": name, "what": name,
                      "detail": _size(_tree_size(path)), "where": path,
                      "when": os.path.getmtime(path)})
    return items


def _shell_kept(local):
    """What the shell keeps: consent to run the unsigned, the program index."""
    if local is None or local.shell is None:
        return None
    try:
        return local.shell("kept.list", {}) or {}
    except Exception:                                   # noqa: BLE001
        return None


def _consents(kept):
    if kept is None:
        return None
    return [{"id": str(one.get("path", "")),
             "what": os.path.basename(str(one.get("path", ""))),
             "detail": "", "where": str(one.get("path", "")),
             "when": float(one.get("at") or 0.0)}
            for one in (kept.get("consents") or [])]


def _program_index(kept):
    if kept is None:
        return None
    count = int(kept.get("index") or 0)
    if not count:
        return []
    return [{"id": "all", "what": tr("Программ в списке: {n}", n=count),
             "detail": "", "where": "", "when": 0.0}]


def _local_groups(local):
    """The groups beside the store, in page order. `None` — cannot be known."""
    kept = _shell_kept(local)
    return [("journals", _journals(local) if local is not None else None),
            ("calls", _calls(local)),
            ("backups", _backups(local)),
            ("consents", _consents(kept)),
            ("program_index", _program_index(kept))]


def _secrets(store):
    """
    The sign-ins kept for Rina and her plugins (`4.0-H11`) — names, never
    values.

    They are not in the settings: the shell keeps them in the Windows
    Credential Manager. Without a shell nobody can tell what is kept there,
    and the group is left out rather than shown empty — an empty group would
    say "nothing kept", which nobody knows.
    """
    if store is None or not store.available():
        return None
    try:
        kept = store.names()
    except Exception:                                   # noqa: BLE001
        return None
    items = []
    for owner, name in kept:
        whose = (owner[len("plugin:"):] if owner.startswith("plugin:")
                 else "Рина")
        items.append({
            "id": _text(f"{owner}/{name}", 200),
            "what": _text(f"{whose}: {name}", 200),
            # The value never: the point of the store is that it is not
            # shown, and this page is the one most likely to be read over a
            # shoulder.
            "detail": "",
            "where": "Диспетчер учётных данных Windows",
            "when": 0.0,
        })
    return items


def inventory(settings, secrets=None, local=None):
    """
    Everything kept about a person, group by group.

    The last loop is the load-bearing one. Every key of the store that no
    group above claims, and that is not a setting, becomes a group under its
    own name — because a kind of personal data added later must appear here
    **without** anybody remembering to add it. A page that answers "this is
    everything" has to be right about that by construction, not by upkeep.
    """
    groups = []
    for name, _keys, read in GROUPS:
        if name == "telemetry":
            items = _telemetry(settings, getattr(local, "telemetry", None))
        else:
            items = read(settings)
        groups.append({"id": name, "count": len(items), "items": items})

    kept = _secrets(secrets)
    if kept is not None:
        groups.append({"id": "secrets", "count": len(kept), "items": kept})

    # Beside the store. A group that cannot be known — no shell to ask —
    # is left out rather than shown empty: empty would say "nothing kept".
    for name, items in _local_groups(local):
        if items is not None:
            groups.append({"id": name, "count": len(items), "items": items})

    changed = _changed_settings(settings)
    groups.append({"id": "settings", "count": len(changed), "items": changed})

    spoken_for = {key for _id, keys, _read in GROUPS for key in keys}
    for key in sorted(settings_schema.DEFAULTS):
        if key in spoken_for or key in settings_schema.SETTABLE:
            continue
        value = settings.get(key, settings_schema.DEFAULTS.get(key))
        items = _unclaimed(key, value)
        groups.append({"id": key, "count": len(items), "items": items})

    return groups


def _unclaimed(key, value):
    """A store of data nothing here knows about, shown as it is."""
    if isinstance(value, dict):
        return [{"id": _text(str(k), 100), "what": _text(str(k), 100),
                 "detail": _text(v, 200), "where": "", "when": 0.0}
                for k, v in value.items()]
    if isinstance(value, (list, tuple)):
        return [{"id": str(at), "what": _text(item), "detail": "",
                 "where": "", "when": 0.0}
                for at, item in enumerate(value)]
    if value in (None, "", 0, False):
        return []
    return [{"id": key, "what": _text(value), "detail": "",
             "where": "", "when": 0.0}]


# ---------------------------------------------------------------------------
# Forgetting (`4.0b-B02`)
# ---------------------------------------------------------------------------
#
# Which key of the store a group lives in, and how an entry is picked out of
# it. Deliberately the *same* table the inventory is built from: a group a
# person can see and cannot forget would be worse than not showing it, and
# two tables would drift into exactly that.


def _drop_from_dict(value, ids):
    """A mapping: the entry's id is its key."""
    kept = {k: v for k, v in value.items() if str(k) not in ids}
    return kept, len(value) - len(kept)


def _drop_from_list(value, ids, key):
    """A list: the entry's id is its own field, or its position."""
    kept = []
    for at, item in enumerate(value):
        named = str(item.get(key, "")) if isinstance(item, dict) else ""
        # An entry with an identifier of its own is matched only by it.
        # Position is the fallback for entries that have none — the
        # journal's, say — and matching both ways would forget the wrong
        # row the first time an id happened to look like a number.
        if named in ids if named else str(at) in ids:
            continue
        kept.append(item)
    return kept, len(value) - len(kept)


def _forget_settings(settings, ids):
    """A preference is forgotten by going back to its default."""
    gone = 0
    for key in list(ids):
        if key not in settings_schema.SETTABLE:
            continue
        default = settings_schema.DEFAULTS.get(key)
        if settings.get(key, default) == default:
            continue
        settings.set(key, default)
        gone += 1
    return gone


#: group id -> (store key, the field an entry is named by)
FORGETTABLE = {
    "aliases": ("app_aliases", None),
    "history": ("history", None),
    "reminders": ("reminders", "id"),
    "todo": ("todo", "id"),
    "sessions": ("sessions", "id"),
    "commands": ("custom_commands", "id"),
    "stats": ("command_stats", None),
    "plugins": ("enabled_plugins", None),
    "folders": ("program_folders", None),
}


def _forget_telemetry(settings, wanted, telemetry=None):
    import io
    import json

    from core.telemetry import SENT_FILE, Telemetry

    telemetry = telemetry or Telemetry(settings)
    gone = 0
    if wanted is None or "pending" in wanted:
        if telemetry.report() is not None:
            gone += 1
        telemetry.forget()
    kept = [one for one in telemetry.sent()
            if wanted is not None and str(one.get("at", "")) not in wanted]
    gone += len(telemetry.sent()) - len(kept)
    path = telemetry._path(SENT_FILE)
    try:
        if kept:
            with io.open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(json.dumps(one, ensure_ascii=False)
                                  for one in kept) + "\n")
        elif os.path.exists(path):
            os.remove(path)
    except OSError:
        pass
    return gone


def _forget_local(local, group, wanted):
    """Forget one of the groups beside the store. How many went; None — not one of them."""
    if group == "journals":
        # Only when asked through the program, never as a side effect of a
        # bare call: the folder is wherever `APPDATA` points.
        if local is None:
            return 0
        from core.logging_setup import forget_journals

        return forget_journals(None if wanted is None else sorted(wanted))
    if group == "calls":
        if local is None or local.audit is None:
            return 0
        count = local.audit.count()
        local.audit.clear()
        return count
    if group == "backups":
        gone = 0
        for item in _backups(local) or []:
            if wanted is not None and item["id"] not in wanted:
                continue
            shutil.rmtree(item["where"], ignore_errors=True)
            gone += 0 if os.path.exists(item["where"]) else 1
        return gone
    if group in ("consents", "program_index"):
        if local is None or local.shell is None:
            return 0
        payload = ({"consents": None if wanted is None else sorted(wanted)}
                   if group == "consents" else {"index": True})
        try:
            answer = local.shell("kept.forget", payload) or {}
        except Exception:                               # noqa: BLE001
            return 0
        return int(answer.get("forgotten") or 0)
    return None


def forget(settings, group, ids=None, secrets=None, local=None):
    """
    Forget entries of one group, or the group entire.

    `ids` of `None` means the whole group. Returns how many entries went —
    a number, because "done" and "there was nothing there" are different
    answers, and a page that says "forgotten" over an entry still on the
    screen teaches a person to distrust the button.

    **A group not in the table above is still forgettable.** It reached the
    page by the walk in `inventory`, and something a person can see and
    cannot remove is worse than something never shown: the page would be
    displaying their data next to a button that quietly does nothing.
    """
    wanted = None if ids is None else {str(i) for i in ids}

    if group == "telemetry":
        # The records, not the choice: forgetting what was gathered and
        # sent is not the same as switching it off, and a button that did
        # both would decide the second for the person.
        return _forget_telemetry(settings, wanted,
                                 getattr(local, "telemetry", None))

    gone_beside = _forget_local(local, group, wanted)
    if gone_beside is not None:
        return gone_beside

    if group == "secrets":
        return _forget_secrets(secrets, wanted)

    if group == "settings":
        if wanted is None:
            wanted = {item["id"] for item in _changed_settings(settings)}
        gone = _forget_settings(settings, wanted)
        settings.save()
        return gone

    key, named = FORGETTABLE.get(group, (group, None))
    if key not in settings_schema.DEFAULTS:
        return 0

    value = settings.get(key, settings_schema.DEFAULTS.get(key))
    empty = settings_schema.DEFAULTS.get(key)

    if wanted is None:
        gone = len(value) if isinstance(value, (dict, list)) else 1
        settings.set(key, type(empty)() if isinstance(empty, (dict, list))
                     else empty)
    elif isinstance(value, dict):
        kept, gone = _drop_from_dict(value, wanted)
        settings.set(key, kept)
    elif isinstance(value, list):
        kept, gone = _drop_from_list(value, wanted, named or "id")
        settings.set(key, kept)
    else:
        gone = 0

    # `plugin_settings` rides along with `enabled_plugins`: they are one
    # group on the page, so forgetting a plugin there has to take what the
    # plugin kept as well. Leaving it would mean a page that says the
    # plugin is forgotten while its store sits underneath.
    if group == "plugins":
        kept_settings = dict(settings.get("plugin_settings", {}) or {})
        for name in list(kept_settings):
            if wanted is None or str(name) in wanted:
                kept_settings.pop(name, None)
                gone += 1
        settings.set("plugin_settings", kept_settings)
        # And its sign-ins (`4.0-H11`), for the same reason: a forgotten
        # plugin whose token stays in the Credential Manager is not
        # forgotten.
        prefix = "plugin:"
        _forget_secrets(secrets, None if wanted is None else
                        {f"{prefix}{one}/" for one in wanted}, owners=True)

    settings.save()
    return gone


def _forget_secrets(store, wanted, owners=False):
    """
    Forget kept sign-ins: these `owner/name` entries, or all when `wanted`
    is None. With `owners`, `wanted` holds `owner/` prefixes. How many went.
    """
    if store is None or not store.available():
        return 0
    try:
        kept = store.names()
    except Exception:                                   # noqa: BLE001
        return 0
    gone = 0
    for owner, name in kept:
        entry = f"{owner}/{name}"
        if wanted is not None:
            hit = (any(entry.startswith(one) for one in wanted) if owners
                   else entry in wanted)
            if not hit:
                continue
        elif owners:
            if not owner.startswith("plugin:"):
                continue
        try:
            gone += store.delete(owner, name)
        except Exception:                               # noqa: BLE001
            continue
    return gone


def forget_everything(settings, secrets=None, local=None):
    """
    Everything kept about a person, in one operation.

    **Everything the page shows**, preferences included: a person pressing
    this on a screen listing eight groups means the eight, not six of them.
    A chosen wake word and a chosen voice are things Rina knows about
    somebody, which is exactly why they are on that page in the first place.

    Group by group rather than by wiping the file. What the program needs in
    order to start — the store's version, whether the wizard has run — is
    not personal data, is not on the page, and is not in `SETTABLE`; going
    through the groups leaves it alone without anybody having to remember a
    list of exceptions.
    """
    gone = 0
    for group in [name for name, _keys, _read in GROUPS] + ["settings"]:
        gone += forget(settings, group, secrets=secrets, local=local)
    gone += _forget_secrets(secrets, None)
    # Beside the store (H-4). The journals last: forgetting is itself
    # written down on the way, and what is erased should include that.
    for group in ("calls", "backups", "consents", "program_index",
                  "journals"):
        gone += forget(settings, group, local=local)
    return gone


def export(settings, secrets=None, local=None):
    """
    Everything kept about a person, as the contents of a file (`4.0b-B03`).

    The same groups the page shows, in the same shape, wrapped in the
    envelope every other export here uses. **The envelope is not decoration:**
    a file whose first line says what it is can be recognised a year later
    by the person who made it and refused by the importer that should not
    take it — and `T-18` is the record of what happens without one.

    The core hands over the contents; the file is written by the shell,
    which is the side that touches the machine (ADR 0009, §6).

    Nothing is dressed up here and nothing is left out: the export is the
    inventory. A file that showed less than the page would make the page a
    summary of itself, and a person exporting their data in order to read
    it elsewhere would be handed a shorter answer for no stated reason.
    """
    from core import data_transfer

    return data_transfer.envelope(data_transfer.KIND_EVERYTHING, {
        "groups": inventory(settings, secrets, local),
    })


def summary(settings):
    """The counts alone — for anything that wants the size, not the content."""
    return {group["id"]: group["count"] for group in inventory(settings)}


def gathered_at():
    return time.time()
