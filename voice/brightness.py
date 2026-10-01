"""
Phrases about the screen's brightness (`4.0b-K04`).

«яркость на 45», «поставь яркость 70 процентов», «сделай ярче», «убавь
яркость», «яркость на максимум», and on their own «ярче», «темнее».

**Parsed before the system phrases, and for a reason.** Those are matched
with a fuzzy fallback for misrecognition, and «убавь яркость» sits close to
«убавь громкость» — the same closeness that once turned «убавь громкость»
into «прибавь». A phrase about brightness is taken here, whole, before the
fuzzy matching gets to see it.

**A bare «темнее» is taken only when nothing else is said.** «Сделай тему
темнее» is about the window's colours, not the screen, so without the word
«яркость» only a short phrase made of these words counts.
"""
import re

#: A phrase is about the brightness when it has one of these roots.
ROOTS = ("яркост", "brightness")

UP = ("ярче", "поярче", "посветлее", "светлее", "прибав", "увелич",
      "повыс", "больше", "brighter", "up", "raise")
DOWN = ("темнее", "потемнее", "убав", "уменьш", "пониз", "меньше",
        "dimmer", "darker", "down", "lower")

#: Words a bare «ярче» / «темнее» may come with and still be about the
#: screen. Anything else in the phrase means it is about something else.
BARE = frozenset({"сделай", "сделать", "экран", "экрана", "чуть", "немного",
                  "ещё", "еще", "пожалуйста", "ну", "давай", "можно",
                  "ярче", "поярче", "посветлее", "светлее", "темнее",
                  "потемнее", "brighter", "dimmer", "darker", "screen",
                  "make", "the", "a", "bit", "please"})

MOST = ("максимум", "максимальн", "на полную", "max")
LEAST = ("минимум", "минимальн", "min")


def _has(low, stems):
    return any(re.search(r"\b" + re.escape(stem), low) for stem in stems)


def classify(text):
    """
    ("set", level), ("up", None), ("down", None) — or None.

    A pure function: the router needs an intent, and the shell does the
    rest.
    """
    low = " ".join(re.findall(r"[\w%]+", str(text or "").lower()
                              .replace("ё", "е")))
    if not low:
        return None
    words = low.split()

    if not _has(low, ROOTS):
        # Without the word «яркость», only a short phrase of the bare words.
        if not set(words) <= BARE:
            return None
        if _has(low, UP[:4] + ("brighter",)):
            return ("up", None)
        if _has(low, DOWN[:2] + ("dimmer", "darker")):
            return ("down", None)
        return None

    number = re.search(r"\b(\d{1,3})\b", low)
    if number:
        return ("set", max(0, min(100, int(number.group(1)))))
    if _has(low, MOST):
        return ("set", 100)
    if _has(low, LEAST):
        return ("set", 0)
    if _has(low, UP):
        return ("up", None)
    if _has(low, DOWN):
        return ("down", None)
    return None
