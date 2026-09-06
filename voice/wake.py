"""
Matching the wake word.

Speech recognition often gives out close but inexact variants: "Рина",
"Рену", "Рино", "Рина,". So the wake word is a LIST of variants (synonyms),
and the comparison is fuzzy (by similarity), to catch the forms the user did
not spell out.

The storage format: settings["wake_words"] is a list of strings. For
backward compatibility the old settings["wake_word"] (one string) is taken
into account too.
"""

import difflib


# The similarity threshold for a fuzzy match (0..1).
# 0.8 catches "рины"/"рино" (0.75 does not pass) and "ирина" (0.89 passes);
# a badly distorted "рену" (0.5) needs the threshold lowered to about 0.5.
# This is the default; the actual one is taken from the settings
# (wake_sensitivity), because a good threshold depends on the microphone and
# the recognition engine.
FUZZY_THRESHOLD = 0.8


def threshold():
    """The threshold from the settings, guarded against meaningless values."""
    try:
        from core.settings_store import settings
        value = float(settings.get("wake_sensitivity", FUZZY_THRESHOLD))
    except Exception:
        return FUZZY_THRESHOLD
    # below 0.5 anything at all will match, above 0.98 almost nothing will
    return max(0.5, min(0.98, value))


def get_wake_words(settings) -> list:
    """Returns the list of the wake word's variants (in lower case)."""
    words = settings.get("wake_words", None)
    result = []
    if isinstance(words, list):
        result = [str(w).strip().lower() for w in words if str(w).strip()]
    # backward compatibility: a single wake_word
    if not result:
        single = str(settings.get("wake_word", "Рина")).strip().lower()
        if single:
            result = [single]
    return result


def _tokenize(text):
    # we split into words, stripping punctuation at the edges
    raw = text.lower().replace(",", " ").replace(".", " ").split()
    return [w.strip(" ,.!:;—-\t") for w in raw if w.strip(" ,.!:;—-\t")]


def find_wake(text, wake_words):
    """
    Looks for the wake word in the text (exactly or fuzzily).
    Returns the index of the token AFTER the activation (for cutting the
    command out), the list of tokens and a found flag:
        (found: bool, tokens: list, cut_index: int)
    cut_index is the index of the command's first token after the wake word.
    """
    tokens = _tokenize(text)
    if not tokens or not wake_words:
        return (False, tokens, 0)

    # multi-word activation variants ("окей рина") we check as a phrase
    for i, tok in enumerate(tokens):
        for wake in wake_words:
            wake_parts = wake.split()
            if len(wake_parts) == 1:
                # one word — an exact containment or a fuzzy match
                if tok == wake or _similar(tok, wake):
                    return (True, tokens, i + 1)
            else:
                # a phrase of several words — we compare a slice of tokens
                seg = tokens[i:i + len(wake_parts)]
                if len(seg) == len(wake_parts):
                    if all(a == b or _similar(a, b)
                           for a, b in zip(seg, wake_parts)):
                        return (True, tokens, i + len(wake_parts))
    return (False, tokens, 0)


def _similar(a, b):
    if a == b:
        return True
    # short words we compare more strictly, so as not to catch too much
    ratio = difflib.SequenceMatcher(None, a, b).ratio()
    return ratio >= threshold()


def strip_wake(text, wake_words):
    """
    If there is a wake word in the text — returns the command after it (may
    be an empty string). If there is no activation — returns None.
    """
    found, tokens, cut = find_wake(text, wake_words)
    if not found:
        return None
    return " ".join(tokens[cut:]).strip()
