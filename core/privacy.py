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
import time

from core import settings_schema


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


#: A group of the inventory: which keys of the store it accounts for, and
#: how to read them out. The key list is what makes the walk below able to
#: tell an accounted-for key from a new one.
GROUPS = (
    ("aliases", ("app_aliases",), _aliases),
    ("history", ("history",), _history),
    ("reminders", ("reminders",), _reminders),
    ("todo", ("todo",), _todo),
    ("commands", ("custom_commands",), _commands),
    ("stats", ("command_stats",), _stats),
    ("plugins", ("enabled_plugins", "plugin_settings"), _plugins),
    ("folders", ("program_folders",), _folders),
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
    out = []
    for key in sorted(settings_schema.SETTABLE):
        if key in spoken_for:
            continue
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


def inventory(settings):
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
        items = read(settings)
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


def summary(settings):
    """The counts alone — for anything that wants the size, not the content."""
    return {group["id"]: group["count"] for group in inventory(settings)}


def gathered_at():
    return time.time()
