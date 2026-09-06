# -*- coding: utf-8 -*-
"""
Which program the person meant.

`4.0-G07`; the decision is
[ADR 0009](../docs/adr/0009-system-layer.md): **the index is
operating-system data and lives in the shell; the matching is language and
lives here.** "Телеграм" → Telegram, "фотошоп" → Photoshop, "вижуал студио"
→ which of the two (and one has to ask again) — that is transliteration,
fuzzy matching and disambiguation, that is, speech.

The argument that settled the fork: later the matching will be improved by a
language model, and that lives in the core. Had we laid this out in the
shell, the very first improvement would have demanded either dragging the
model there or bringing the logic back.

The module knows nothing about Windows: neither the registry, nor the Start
menu, nor `PATH`. It is handed a list of entries — where that came from is
none of its business. That is why `find()` requires `entries`: it has
nothing to go and look with, and that is a boundary rather than an
unfinished job.
"""

from voice.textmatch import has_cyrillic, normalize, similar, translit


# Spoken names -> what the program is called in the system.
# Transliteration pulls a lot across ("блендер" -> blender), but not
# everything: "хром" -> hrom, "стим" -> stim, "ворд" -> vord — here a direct
# hint is needed.
SPOKEN_ALIASES = {
    "хром": "chrome", "гугл хром": "chrome", "гуглхром": "chrome",
    "ворд": "word", "эксель": "excel", "поверпоинт": "powerpoint",
    "аутлук": "outlook", "оутлук": "outlook",
    "стим": "steam", "фотошоп": "photoshop", "фотошок": "photoshop",
    "телега": "telegram", "телеграмм": "telegram",
    "фаерфокс": "firefox", "файрфокс": "firefox", "фokc": "firefox",
    "опера": "opera", "яндекс": "yandex", "яндекс браузер": "yandex",
    "скайп": "skype", "зум": "zoom", "вайбер": "viber", "ватсап": "whatsapp",
    "спотифай": "spotify", "стимул": "steam",
    "обс": "obs", "вскод": "code", "вс код": "code", "вижуал студио": "visual studio",
    "питон": "python", "юнити": "unity", "анрил": "unreal",
    "премьер": "premiere", "иллюстратор": "illustrator", "автокад": "autocad",
    "майнкрафт": "minecraft", "эпик": "epic", "эпик геймс": "epic games",
    "проводник": "explorer",
    "клод": "claude", "клауд": "claude", "чатгпт": "chatgpt", "гпт": "chatgpt",
    "брейв": "brave", "эдж": "edge", "едж": "edge",
    "обсидиан": "obsidian", "стим": "steam",
    "терминал": "terminal", "командная строка": "cmd",
}

# A browser is not a program's name but a role: one person has Brave
# installed, another Edge. We look for the first installed one from the list
# (order = priority).
BROWSER_WORDS = ("браузер", "browser", "интернет")
KNOWN_BROWSERS = ("chrome", "brave", "firefox", "edge", "opera", "yandex",
                  "vivaldi", "chromium")


class AppEntry:
    """One application that was found."""

    __slots__ = ("name", "launch", "kind", "source")

    def __init__(self, name, launch, kind, source):
        self.name = name        # the display name ("Telegram Desktop")
        self.launch = launch    # what to launch (a path to .lnk/.exe, or an AppID)
        self.kind = kind        # "file" | "uwp"
        self.source = source    # "start_menu" | "uwp" | "path"

    @property
    def key(self):
        return normalize(self.name)

    def to_dict(self):
        return {"name": self.name, "launch": self.launch,
                "kind": self.kind, "source": self.source}

    @classmethod
    def from_dict(cls, d):
        return cls(d.get("name", ""), d.get("launch", ""),
                   d.get("kind", "file"), d.get("source", "start_menu"))

    def __repr__(self):
        return f"<AppEntry {self.name!r} [{self.source}]>"


def query_variants(query):
    """
    Spellings of the query: as it was said, transliterated, and by the table
    of spoken names. "фотошоп" is looked for both as "fotoshop" and as
    "photoshop".
    """
    norm = normalize(query)
    if not norm:
        return []
    variants = [norm]
    alias = SPOKEN_ALIASES.get(norm)
    if alias:
        variants.append(normalize(alias))
    if has_cyrillic(norm):
        variants.append(translit(norm))
    # unique, non-empty, in the original order of priority
    seen, result = set(), []
    for v in variants:
        if v and v not in seen:
            seen.add(v)
            result.append(v)
    return result


# Programs from PATH are hundreds of utility .exe files (antiword, mobsync
# and so on). We let them into the results only on a confident match, or
# they crowd out the normal applications from the Start menu.
MIN_SCORE_PATH = 80


def _score(key, variant):
    if key == variant:
        return 100
    # a match with a whole word matters more than a match with the beginning
    # of a long word: "обс" -> "OBS Studio", not "Obsidian"
    if variant in key.split():
        return 90
    if key.startswith(variant):
        return 80
    if variant in key:
        return 60
    if similar(key, variant):
        return 40
    return 0


def is_browser_query(query):
    """They are asking for "a browser" in general, not for a particular program."""
    variants = query_variants(query)
    return bool(variants) and variants[0] in BROWSER_WORDS


def _find_browser(entries):
    """The installed browsers in the order of priority from KNOWN_BROWSERS."""
    result = []
    for wanted in KNOWN_BROWSERS:
        for entry in entries:
            words = entry.key.split()
            if wanted in words or entry.key.startswith(wanted):
                if entry not in result:
                    result.append(entry)
    return result


def find(query, limit=5, entries=None):
    """
    Candidates for the query, from best to worst.

    The ranking: an exact name → begins with the query → contains it →
    resembles it. Precision matters more than completeness: launching the
    wrong program is more unpleasant than asking again.

    `entries` is required, even though it has a default: this module has
    nothing to go and look with — the index is assembled by the shell
    (ADR 0009). An empty list gives an empty answer rather than a trip into
    the system.
    """
    variants = query_variants(query)
    if not variants or not entries:
        return []

    # "launch a browser" — they are asking for a role, not a particular name
    if variants[0] in BROWSER_WORDS:
        found = _find_browser(entries)
        return found[:limit]

    scored = []
    for entry in entries:
        key = entry.key
        if not key:
            continue
        best = 0
        for i, variant in enumerate(variants):
            value = _score(key, variant)
            if value:
                # the "as it was said" variant matters slightly more than the derived ones
                value -= i
                best = max(best, value)
        if not best:
            continue
        if entry.source == "path" and best < MIN_SCORE_PATH:
            continue
        # with an equal match, the shorter name is usually the one wanted
        scored.append((best, -len(key), entry))

    scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
    return [entry for _s, _l, entry in scored[:limit]]
