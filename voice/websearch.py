"""
Веб-поиск: явные команды («найди рецепт борща») и запасной вариант,
когда команда не распознана ни одним обработчиком.

Поисковая система выбирается настройкой search_engine. Запрос уходит в
браузер по умолчанию — ничего никуда не отправляется мимо него.
"""

import re
import urllib.parse
import webbrowser

from core.i18n import t as tr


# фразы, после которых идёт поисковый запрос
TRIGGERS = (
    "найди в интернете", "поищи в интернете", "найди в сети",
    "загугли", "погугли", "найди", "поищи", "поиск",
    "search for", "search", "google", "look up",
)

ENGINES = {
    "google": ("Google", "https://www.google.com/search?q={q}"),
    "yandex": ("Яндекс", "https://yandex.ru/search/?text={q}"),
    "duckduckgo": ("DuckDuckGo", "https://duckduckgo.com/?q={q}"),
    "bing": ("Bing", "https://www.bing.com/search?q={q}"),
}
DEFAULT_ENGINE = "google"


def engine_choices():
    """[(id, label)] для выпадающего списка в настройках."""
    return [(eid, label) for eid, (label, _) in ENGINES.items()]


def engine_label(engine_id):
    return ENGINES.get(engine_id, ENGINES[DEFAULT_ENGINE])[0]


def search_url(query, engine_id=DEFAULT_ENGINE):
    _, template = ENGINES.get(engine_id, ENGINES[DEFAULT_ENGINE])
    return template.format(q=urllib.parse.quote_plus(query))


def open_search(query, engine_id=DEFAULT_ENGINE):
    """Открывает поиск в браузере. True при успехе."""
    query = (query or "").strip()
    if not query:
        return False
    try:
        webbrowser.open(search_url(query, engine_id))
        return True
    except Exception:
        return False


def extract_query(text):
    """
    Возвращает поисковый запрос, если фраза начинается с поискового триггера,
    иначе None. Триггеры проверяются от длинных к коротким, чтобы
    «найди в интернете X» не превратилось в «в интернете X».
    """
    if not text:
        return None
    low = text.lower().strip()
    for trigger in sorted(TRIGGERS, key=len, reverse=True):
        if low.startswith(trigger):
            query = text.strip()[len(trigger):]
            query = re.sub(r"^[\s,:—-]+", "", query).strip()
            return query or None
    return None


def try_search(text, engine_id=DEFAULT_ENGINE):
    """
    Обрабатывает явную поисковую команду.
    Возвращает текст ответа или None, если фраза не про поиск.
    """
    query = extract_query(text)
    if not query:
        return None
    if open_search(query, engine_id):
        return tr("Ищу «{query}» в {engine}.",
                  query=query, engine=engine_label(engine_id))
    return tr("Не удалось открыть браузер для поиска.")


def fallback_search(text, engine_id=DEFAULT_ENGINE):
    """
    Запасной вариант для нераспознанной команды: ищем её текст целиком.
    Возвращает текст ответа или None, если открыть браузер не вышло.
    """
    text = (text or "").strip()
    if not text:
        return None
    if open_search(text, engine_id):
        return tr("Не нашла такой команды — поищу «{query}» в интернете.",
                  query=text)
    return None
