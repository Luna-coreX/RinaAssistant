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
from core.i18n import t as tr


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


def forget(settings, group, ids=None):
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

    settings.save()
    return gone


def forget_everything(settings):
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
        gone += forget(settings, group)
    return gone


def export(settings):
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
        "groups": inventory(settings),
    })


def summary(settings):
    """The counts alone — for anything that wants the size, not the content."""
    return {group["id"]: group["count"] for group in inventory(settings)}


def gathered_at():
    return time.time()
