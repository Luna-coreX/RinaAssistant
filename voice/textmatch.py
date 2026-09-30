"""
Fuzzy matching of commands.

Speech recognition almost never gives out a phrase exactly as the user typed
it: "запусти дискорд" turns into "запусти Дискорд,", "зопусти дискорт" and
so on. An exact substring containment does not catch such variants, so the
comparison goes in three steps: normalisation → containment → fuzzy
comparison.

The threshold is deliberately high: a command firing falsely (launching the
wrong program) is more unpleasant than having to repeat the phrase.
"""

import difflib
import re


THRESHOLD = 0.82        # the minimum similarity for a fuzzy match
MIN_FUZZY_LEN = 4       # short words we compare only exactly


def normalize(text):
    """Brings a phrase to a comparable form: case, ё, punctuation, spaces."""
    if not text:
        return ""
    low = str(text).lower().replace("ё", "е")
    low = re.sub(r"[^\w\s]+", " ", low, flags=re.UNICODE)
    return re.sub(r"\s+", " ", low).strip()


# Cyrillic -> Latin. Needed because speech recognition always gives out
# Russian letters ("телеграм"), while program names are almost always in
# Latin.
_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ж": "zh",
    "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n",
    "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f",
    "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "",
    "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


def translit(text):
    """"телеграм" -> "telegram". Latin stays as it is."""
    norm = normalize(text)
    return "".join(_TRANSLIT.get(ch, ch) for ch in norm)


def has_cyrillic(text):
    return any("а" <= ch <= "я" or ch == "ё" for ch in str(text).lower())


def similar(a, b, threshold=THRESHOLD):
    """Are two strings similar (after normalisation)."""
    a, b = normalize(a), normalize(b)
    if not a or not b:
        return False
    if a == b:
        return True
    if len(a) < MIN_FUZZY_LEN or len(b) < MIN_FUZZY_LEN:
        return False
    return difflib.SequenceMatcher(None, a, b).ratio() >= threshold


def whole_word(haystack, needle) -> bool:
    """
    Is `needle` in `haystack` as a word of its own, not inside another.

    **The third time this bit.** «пока» lives inside «покажи», so
    «покажи задачи» was answered «До встречи». «техно» lives inside
    «технологиями», so «как успехи с технологиями для полного
    погружения» was taken for a request to put on some techno. Both
    were tables matched with `in`, both answers were real answers to a
    phrase nobody said, and nothing anywhere said so — which is what
    makes this failure worth one function rather than three fixes.

    A phrase of several words is looked for as a substring: its own
    length is the boundary, and «включи музыку» cannot hide inside
    another word. A single word is compared with the words of what was
    said.

    **This is not right for every table, and the difference is the
    point.** Russian inflects, and `voice/todo.py` matches «сделал»
    against «сделала» on purpose — there `in` is doing prefix work and
    taking it away would lose the ending. Tables of nouns and fixed
    phrases want this function; tables of verb stems want what they
    have. What none of them wants is to decide by accident.
    """
    hay, ned = normalize(haystack), normalize(needle)
    if not hay or not ned:
        return False
    if " " in ned:
        return ned in hay
    return ned in hay.split()


def contains_phrase(haystack, needle, threshold=THRESHOLD):
    """
    Is the phrase `needle` inside `haystack` — exactly or with typos.

    We slide a window as long as the phrase's word count: "включи мне
    дискорд сейчас" must find "включи дискорд" allowing for recognition
    inexactness.
    """
    hay, ned = normalize(haystack), normalize(needle)
    if not hay or not ned:
        return False
    if ned in hay:
        return True

    hay_words = hay.split()
    ned_words = ned.split()
    span = len(ned_words)
    if not hay_words or span > len(hay_words):
        # the phrase is longer than what was said — we compare it whole
        return similar(hay, ned, threshold)

    for i in range(len(hay_words) - span + 1):
        window = " ".join(hay_words[i:i + span])
        if similar(window, ned, threshold):
            return True
    return False


#: "the second one", "two", "2" — how a person points at an option by its
#: place in a list.
#:
#: Here rather than next to the programs, because this is language and not
#: launching: the same words pick a thing off the list of things to do. Two
#: copies of a table like this part company on the first word added to one
#: of them.
ORDINALS = {
    "первый": 0, "первое": 0, "первая": 0, "первую": 0, "1": 0, "один": 0,
    "второй": 1, "второе": 1, "вторая": 1, "вторую": 1, "2": 1, "два": 1,
    "третий": 2, "третье": 2, "третья": 2, "третью": 2, "3": 2, "три": 2,
    "first": 0, "second": 1, "third": 2,
}

CANCEL_WORDS = ("отмена", "отмени", "неважно", "ничего", "забудь", "никакое",
                "cancel", "never mind", "nothing")


def pick(said, titles):
    """
    Which of the offered lines the person named. `(index | None, cancelled)`.

    By place ("the second"), by the whole name, or by a part of it — a
    person answering about "buy milk and bread" says "milk". The part only
    counts when exactly one line contains it: if two do, we are back where
    the question started and guessing would defeat the point of asking.
    """
    low = normalize(said)
    if not low:
        return None, False
    if any(word in low for word in CANCEL_WORDS):
        return None, True

    for word in low.split():
        if word in ORDINALS and ORDINALS[word] < len(titles):
            return ORDINALS[word], False

    index, _ = best_match(low, titles)
    if index is not None:
        return index, False

    inside = [i for i, title in enumerate(titles) if low in normalize(title)]
    if len(inside) == 1:
        return inside[0], False
    return None, False


def best_match(text, candidates, threshold=THRESHOLD):
    """
    Returns (index, coefficient) of the most similar candidate, or (None, 0).
    Used when the best option has to be chosen rather than the first
    suitable one.
    """
    norm = normalize(text)
    best_i, best_ratio = None, 0.0
    for i, candidate in enumerate(candidates):
        cand = normalize(candidate)
        if not cand:
            continue
        ratio = 1.0 if cand == norm else difflib.SequenceMatcher(
            None, norm, cand).ratio()
        if ratio > best_ratio:
            best_i, best_ratio = i, ratio
    if best_i is not None and best_ratio >= threshold:
        return best_i, best_ratio
    return None, 0.0
