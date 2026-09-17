"""
Music: what to put on, and what to put it on with.

A domain of its own and a small one. It exists because "включи музыку"
is the plainest thing a person says to an assistant and the one this
one answered with "Не нашла программу «музыку»" — the launcher took it,
because nothing else would.

**Nothing is played here.** The genre is turned into a search on a
video site and the browser is asked to open it, through the same tool
and the same permission as any other search. Naming a particular
channel would be a promise that rots: a link that is the best one
today is a dead link in a year, and a person told "включаю Lo-Fi Girl"
and shown an error is worse off than one told what was actually done.
"""

import re

from voice.textmatch import normalize

#: What counts as asking for music without saying which.
ASK_PHRASES = ("включи музыку", "поставь музыку", "давай музыку",
               "music", "включи музычку", "хочу музыку")

#: Suggestions, not a list. They are what Rina offers when asked to
#: choose for the person; any other answer is taken as said.
SUGGESTED = ("Lo-Fi", "Ambient")

#: Ways of saying "put on X" where X is the music.
PUT_ON = ("включи", "поставь", "врубай", "врубить", "давай", "play")

#: Words that belong to the asking rather than to the genre, and are
#: cut out of it: "включи спокойную музыку для работы" is a request for
#: "спокойную ... для работы", not for a genre called "музыку".
NOT_THE_GENRE = ("музыку", "музыка", "музычку", "music", "трек", "треки",
                 "песню", "песни", "что-нибудь", "чего-нибудь")


#: Genres Rina knows by name, so that "включи джаз" does not have to
#: be asked about. Short on purpose: it is a convenience, not a
#: catalogue — everything not in it still works through the question,
#: which takes any answer. A long list here would be a list nobody
#: keeps up and a list that starts swallowing other words.
GENRES = ("lo-fi", "lofi", "лоу-фай", "лофай", "лоуфай",
          "ambient", "эмбиент", "эмбиэнт",
          "jazz", "джаз", "classical", "классику", "классика",
          "rock", "рок", "метал", "metal", "шансон", "поп", "pop",
          "электронную", "электронная", "техно", "techno", "хаус", "house")


def about_music(text) -> bool:
    """
    Is this about music at all.

    **The gate, and it has to be a gate.** Without it "включи блокнот"
    would be a request for the genre "блокнот": the verb is the same,
    and only the rest of the phrase says which of the two it is. The
    launcher is where "включи X" belongs by default, and music takes
    only what names itself.
    """
    low = normalize(text or "")
    if not low:
        return False
    words = set(low.split())
    if words & set(NOT_THE_GENRE):
        return True
    # Compared in the normalised form on both sides: `normalize` drops
    # the hyphen, so "lo-fi" in the list never matches "lo fi" in what
    # was said — and "включи lo-fi" went to the launcher.
    return any(normalize(genre) in low for genre in GENRES)


def asked_without_saying_which(text) -> bool:
    """«Включи музыку» — asking for music and not saying which."""
    low = normalize(text or "")
    if not low:
        return False
    if low in ("музыку", "музыка", "music"):
        return True
    return any(low == phrase or low.startswith(phrase + " ")
               and not _genre_after(low, phrase)
               for phrase in ASK_PHRASES)


def _genre_after(low, phrase):
    rest = low[len(phrase):].strip()
    rest = " ".join(w for w in rest.split() if w not in NOT_THE_GENRE)
    return rest


def genre_in(text):
    """The genre a person named, or `None` if they named none."""
    low = normalize(text or "")
    if not low:
        return None
    for verb in PUT_ON:
        if low.startswith(verb + " "):
            rest = low[len(verb):].strip()
            words = [w for w in rest.split() if w not in NOT_THE_GENRE]
            # "для работы", "на фон" — the occasion, not the genre, and
            # a search for "lo-fi для работы" finds the same thing as a
            # search for "lo-fi" plus some noise.
            rest = " ".join(words)
            rest = re.sub(r"\b(для|на|под)\s+\w+\s*$", "", rest).strip()
            return rest or None
    return None


def search_for(genre: str) -> str:
    """What to look for: a genre, and the fact that it is to listen to."""
    genre = (genre or "").strip()
    return f"{genre} radio" if genre else "music radio"
