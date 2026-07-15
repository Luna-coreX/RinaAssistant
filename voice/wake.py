"""
Сопоставление слова активации.

Распознавание речи часто выдаёт близкие, но не точные варианты: «Рина»,
«Рену», «Рино», «Рина,». Поэтому слово активации — это СПИСОК вариантов
(синонимов), а сравнение — нечёткое (по схожести), чтобы ловить и те формы,
что пользователь явно не вписал.

Формат хранения: settings["wake_words"] — список строк. Для обратной
совместимости учитывается и старое settings["wake_word"] (одна строка).
"""

import difflib


# порог схожести для нечёткого совпадения (0..1). 0.8 — «рену»≈«рина».
FUZZY_THRESHOLD = 0.8


def get_wake_words(settings) -> list:
    """Возвращает список вариантов слова активации (в нижнем регистре)."""
    words = settings.get("wake_words", None)
    result = []
    if isinstance(words, list):
        result = [str(w).strip().lower() for w in words if str(w).strip()]
    # обратная совместимость: одиночное wake_word
    if not result:
        single = str(settings.get("wake_word", "Рина")).strip().lower()
        if single:
            result = [single]
    return result


def _tokenize(text):
    # разбиваем на слова, убирая пунктуацию по краям
    raw = text.lower().replace(",", " ").replace(".", " ").split()
    return [w.strip(" ,.!:;—-\t") for w in raw if w.strip(" ,.!:;—-\t")]


def find_wake(text, wake_words):
    """
    Ищет слово активации в тексте (точно или нечётко).
    Возвращает индекс токена ПОСЛЕ активации (для вырезания команды),
    список токенов и признак найденности:
        (found: bool, tokens: list, cut_index: int)
    cut_index — индекс первого токена команды после слова активации.
    """
    tokens = _tokenize(text)
    if not tokens or not wake_words:
        return (False, tokens, 0)

    # многословные варианты активации («окей рина») проверяем как фразу
    for i, tok in enumerate(tokens):
        for wake in wake_words:
            wake_parts = wake.split()
            if len(wake_parts) == 1:
                # одно слово — точное вхождение или нечёткое совпадение
                if tok == wake or _similar(tok, wake):
                    return (True, tokens, i + 1)
            else:
                # фраза из нескольких слов — сравниваем срез токенов
                seg = tokens[i:i + len(wake_parts)]
                if len(seg) == len(wake_parts):
                    if all(a == b or _similar(a, b)
                           for a, b in zip(seg, wake_parts)):
                        return (True, tokens, i + len(wake_parts))
    return (False, tokens, 0)


def _similar(a, b):
    if a == b:
        return True
    # короткие слова сравниваем строже, чтобы не ловить лишнее
    ratio = difflib.SequenceMatcher(None, a, b).ratio()
    return ratio >= FUZZY_THRESHOLD


def strip_wake(text, wake_words):
    """
    Если в тексте есть слово активации — возвращает команду после него
    (может быть пустой строкой). Если активации нет — возвращает None.
    """
    found, tokens, cut = find_wake(text, wake_words)
    if not found:
        return None
    return " ".join(tokens[cut:]).strip()
