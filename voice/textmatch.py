"""
Нечёткое сопоставление команд.

Распознавание речи почти никогда не выдаёт фразу точно так, как её вписал
пользователь: «запусти дискорд» превращается в «запусти Дискорд,», «зопусти
дискорт» и т.п. Точное вхождение подстроки такие варианты не ловит, поэтому
сравнение идёт в три шага: нормализация → вхождение → нечёткое сравнение.

Порог намеренно высокий: ложное срабатывание команды (запуск не той
программы) неприятнее, чем необходимость повторить фразу.
"""

import difflib
import re


THRESHOLD = 0.82        # минимальная схожесть для нечёткого совпадения
MIN_FUZZY_LEN = 4       # короткие слова сравниваем только точно


def normalize(text):
    """Приводит фразу к сравнимому виду: регистр, ё, пунктуация, пробелы."""
    if not text:
        return ""
    low = str(text).lower().replace("ё", "е")
    low = re.sub(r"[^\w\s]+", " ", low, flags=re.UNICODE)
    return re.sub(r"\s+", " ", low).strip()


def similar(a, b, threshold=THRESHOLD):
    """Похожи ли две строки (после нормализации)."""
    a, b = normalize(a), normalize(b)
    if not a or not b:
        return False
    if a == b:
        return True
    if len(a) < MIN_FUZZY_LEN or len(b) < MIN_FUZZY_LEN:
        return False
    return difflib.SequenceMatcher(None, a, b).ratio() >= threshold


def contains_phrase(haystack, needle, threshold=THRESHOLD):
    """
    Есть ли фраза `needle` внутри `haystack` — точно или с опечатками.

    Скользим окном длиной в число слов фразы: «включи мне дискорд сейчас»
    должно находить «включи дискорд» с поправкой на неточность распознавания.
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
        # фраза длиннее сказанного — сравниваем целиком
        return similar(hay, ned, threshold)

    for i in range(len(hay_words) - span + 1):
        window = " ".join(hay_words[i:i + span])
        if similar(window, ned, threshold):
            return True
    return False


def best_match(text, candidates, threshold=THRESHOLD):
    """
    Возвращает (индекс, коэффициент) наиболее похожего кандидата или (None, 0).
    Используется, когда нужно выбрать лучший вариант, а не первый подходящий.
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
