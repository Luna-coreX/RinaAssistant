"""
Launching programs by name: "запусти телеграм", "открой блокнот".

The list used to be hard-coded (five programs); now the name is looked up in
the index of installed applications (voice/app_index.py). If several suit,
we do not guess but return a list of candidates so the assistant can ask
again: launching the wrong program is more unpleasant than asking a
clarifying question.
"""

import os
import re

from core.i18n import t as tr
from voice import app_index
from voice.textmatch import normalize


LAUNCH_VERBS = (
    "запусти", "запустить", "открой", "открыть", "включи", "включить",
    "стартани", "launch", "open", "start", "run",
)

# Filler words after the verb: "запусти мне программу телеграм"
FILLER_WORDS = (
    "мне", "пожалуйста", "программу", "приложение", "прогу", "плиз",
    "давай", "please", "the", "app", "application",
)

# How far apart the candidates must be to pick the first without asking
DECISIVE_GAP = 10


class LaunchOutcome:
    """The result of an attempt to launch: what to say and whether a clarifying question is needed."""

    def __init__(self, status, message, options=None, query=""):
        self.status = status          # "launched" | "ambiguous" | "not_found"
        self.message = message
        self.options = options or []
        self.query = query            # what was looked for (needed for "remember the path")


# ---------------------------------------------------------------------------
# Programs the user has remembered
# ---------------------------------------------------------------------------
def _aliases():
    from core.settings_store import settings
    return dict(settings.get("app_aliases", {}) or {})


def remember(query, path, kind="file", name=None):
    """
    Remember that "ренпай" is this particular program.

    Kept as a dict, because it is not only the path that has to be
    remembered: Store applications have an AppUserModelID instead of a file,
    and checking whether it exists on disk is meaningless.
    """
    from core.settings_store import settings
    key = normalize(query)
    if not key or not path:
        return False
    aliases = _aliases()
    aliases[key] = {
        "path": path,
        "kind": kind,
        "name": name or os.path.splitext(os.path.basename(path))[0],
    }
    settings.set("app_aliases", aliases)
    settings.save()
    return True


def forget(query):
    from core.settings_store import settings
    aliases = _aliases()
    if aliases.pop(normalize(query), None) is None:
        return False
    settings.set("app_aliases", aliases)
    settings.save()
    return True


def alias_lookup(target, aliases):
    """
    The remembered program for a query — from the dict passed in.

    Pure: it reads nothing from the settings and, unlike alias_entry, does
    not clear out stale entries. The router needs a decision, not tidying
    up.
    """
    saved = (aliases or {}).get(normalize(target))
    if not saved:
        return None
    if isinstance(saved, str):
        saved = {"path": saved, "kind": "file",
                 "name": os.path.splitext(os.path.basename(saved))[0]}
    path = saved.get("path")
    if not path:
        return None
    kind = saved.get("kind", "file")
    if kind == "file" and not os.path.exists(path):
        return None
    return app_index.AppEntry(
        saved.get("name") or os.path.splitext(os.path.basename(path))[0],
        path, kind, "learned")


class LaunchDecision:
    """What to launch — before any launching."""

    def __init__(self, status, entry=None, options=None, query=""):
        self.status = status          # "launch" | "ambiguous" | "not_found"
        self.entry = entry
        self.options = options or []
        self.query = query


def decide(text, apps=None, aliases=None):
    """
    A pure decision about launching: what would be launched, launching
    nothing.

    Exactly the same choosing logic as in resolve(), but without side
    effects — for the router's sake (4.0-B02). resolve() remains that same
    decision plus the execution.
    """
    target = extract_target(text)
    if not target:
        return None

    learned = alias_lookup(target, aliases)
    if learned is not None:
        return LaunchDecision("launch", entry=learned, query=target)

    candidates = app_index.find(target, limit=5, entries=apps)
    if not candidates:
        return LaunchDecision("not_found", query=target)

    decisive = len(candidates) == 1 or app_index.is_browser_query(target)
    if not decisive:
        top = app_index.find(target, limit=2, entries=apps)
        if len(top) >= 2:
            scores = [_candidate_score(target, e) for e in top[:2]]
            decisive = (scores[0] - scores[1]) >= DECISIVE_GAP

    if decisive:
        return LaunchDecision("launch", entry=candidates[0], query=target)
    return LaunchDecision("ambiguous", options=candidates[:3], query=target)


def alias_entry(target):
    """The remembered program for this query (or None)."""
    saved = _aliases().get(normalize(target))
    if not saved:
        return None

    # the old format — simply a string with a path
    if isinstance(saved, str):
        saved = {"path": saved, "kind": "file",
                 "name": os.path.splitext(os.path.basename(saved))[0]}

    path = saved.get("path")
    if not path:
        return None
    kind = saved.get("kind", "file")
    # Store applications have an identifier instead of a path — there is nothing to check
    if kind == "file" and not os.path.exists(path):
        forget(target)          # the path is stale — we keep no rubbish
        return None
    name = saved.get("name") or os.path.splitext(os.path.basename(path))[0]
    return app_index.AppEntry(name, path, kind, "learned")


def extract_target(text):
    """
    Returns the program's name after the launching verb, or None if the
    phrase is not about launching at all.
    """
    if not text:
        return None
    low = normalize(text)
    if not low:
        return None

    words = low.split()
    verb_at = None
    for i, word in enumerate(words):
        if word in LAUNCH_VERBS:
            verb_at = i
            break
    if verb_at is None:
        return None

    rest = [w for w in words[verb_at + 1:] if w not in FILLER_WORDS]
    target = " ".join(rest).strip()
    return target or None


def _fallback_catalog(target):
    """
    A fallback catalogue for systems where the index is empty (not Windows).
    Uses the former hard-coded list from voice/commands.py.
    """
    try:
        from voice.commands import APPS, _launch
    except Exception:
        return None
    for key, app in APPS.items():
        if any(name in target for name in app["names"]):
            if _launch(key):
                return tr("Хорошо, запускаю {app}.", app=tr(app["label"]))
            return tr("Не получилось запустить {app} — возможно, "
                      "приложение не установлено.", app=tr(app["label"]))
    return None


def resolve(text):
    """
    Handles a launch command.
    Returns a LaunchOutcome, or None if the phrase is not about launching a
    program.
    """
    target = extract_target(text)
    if not target:
        return None

    # what the user pointed at by hand matters more than search results
    learned = alias_entry(target)
    if learned is not None:
        if app_index.launch(learned):
            return LaunchOutcome(
                "launched", tr("Запускаю {app}.", app=learned.name))
        return LaunchOutcome(
            "not_found",
            tr("Не получилось запустить {app} — программу удалили "
               "или перенесли.", app=learned.name),
            query=target)

    candidates = app_index.find(target, limit=5)

    if not candidates:
        message = _fallback_catalog(target)
        if message:
            return LaunchOutcome("launched", message)
        return LaunchOutcome(
            "not_found",
            tr("Не нашла программу «{name}».", name=target),
            query=target)

    # one candidate or a clear leader — we launch without asking.
    # "запусти браузер" we do not ask about either: they are asking for a
    # role rather than a particular program — we take the first by priority,
    # as the system does.
    decisive = len(candidates) == 1 or app_index.is_browser_query(target)
    if not decisive:
        top = app_index.find(target, limit=2)
        if len(top) >= 2:
            scores = [_candidate_score(target, e) for e in top[:2]]
            decisive = (scores[0] - scores[1]) >= DECISIVE_GAP

    if decisive:
        entry = candidates[0]
        if app_index.launch(entry):
            return LaunchOutcome(
                "launched", tr("Запускаю {app}.", app=entry.name))
        return LaunchOutcome(
            "not_found",
            tr("Не получилось запустить {app} — программу удалили "
               "или перенесли.", app=entry.name))

    names = ", ".join(e.name for e in candidates[:3])
    return LaunchOutcome(
        "ambiguous",
        tr("Нашла несколько: {names}. Какое запустить?", names=names),
        options=candidates[:3], query=target)


def _candidate_score(target, entry):
    """Scoring a candidate the same way as in the index (to compare a pair)."""
    best = 0
    for variant in app_index.query_variants(target):
        best = max(best, app_index._score(entry.key, variant))
    return best


# ---------------------------------------------------------------------------
# The answer to a clarifying question
# ---------------------------------------------------------------------------
ORDINALS = {
    "первый": 0, "первое": 0, "первая": 0, "первую": 0, "1": 0, "один": 0,
    "второй": 1, "второе": 1, "вторая": 1, "вторую": 1, "2": 1, "два": 1,
    "третий": 2, "третье": 2, "третья": 2, "третью": 2, "3": 2, "три": 2,
    "first": 0, "second": 1, "third": 2,
}

CANCEL_WORDS = ("отмена", "отмени", "неважно", "ничего", "забудь", "никакое",
                "cancel", "never mind", "nothing")


def choose(text, options):
    """
    Chooses one of the offered options by the user's answer.
    Returns (entry | None, cancelled: bool).
    """
    low = normalize(text)
    if not low:
        return None, False
    if any(word in low for word in CANCEL_WORDS):
        return None, True

    # "второй", "два", "2"
    for word in low.split():
        if word in ORDINALS:
            idx = ORDINALS[word]
            if idx < len(options):
                return options[idx], False

    # "obs studio" — by name
    ranked = app_index.find(low, limit=1, entries=options)
    if ranked:
        return ranked[0], False
    return None, False
