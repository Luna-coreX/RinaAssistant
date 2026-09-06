"""
Web search: explicit commands ("найди рецепт борща") and the fallback for
when a command was recognised by no handler.

The search engine is chosen by the search_engine setting. The query goes to
the default browser — nothing is sent anywhere past it.
"""

import re
import urllib.parse
import webbrowser

from core.i18n import t as tr


# phrases after which a search query follows
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
    """[(id, label)] for the dropdown in the settings."""
    return [(eid, label) for eid, (label, _) in ENGINES.items()]


def engine_label(engine_id):
    return ENGINES.get(engine_id, ENGINES[DEFAULT_ENGINE])[0]


def search_url(query, engine_id=DEFAULT_ENGINE):
    _, template = ENGINES.get(engine_id, ENGINES[DEFAULT_ENGINE])
    return template.format(q=urllib.parse.quote_plus(query))


def open_search(query, engine_id=DEFAULT_ENGINE):
    """Opens a search in the browser. True on success."""
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
    Returns the search query if the phrase begins with a search trigger,
    otherwise None. The triggers are checked from long to short, so that
    "найди в интернете X" does not turn into "в интернете X".
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
    Handles an explicit search command.
    Returns the text of an answer, or None if the phrase is not about
    searching.
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
    The fallback for an unrecognised command: we search for its text whole.
    Returns the text of an answer, or None if the browser could not be
    opened.
    """
    text = (text or "").strip()
    if not text:
        return None
    if open_search(text, engine_id):
        return tr("Не нашла такой команды — поищу «{query}» в интернете.",
                  query=text)
    return None
