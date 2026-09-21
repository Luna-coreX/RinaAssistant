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
from core.logging_setup import get_logger

log = get_logger("websearch")


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


#: Where music lives. Not among `ENGINES`: those are things a person
#: picks between in the settings, and this is not a choice — it is
#: where a video of a genre is, and picking Bing instead would not be
#: a preference but a mistake.
VIDEO_URL = "https://www.youtube.com/results?search_query={q}"


def youtube_url(query):
    """A search on the video site — for music (`4.0b-E06`)."""
    return VIDEO_URL.format(q=urllib.parse.quote_plus(query or ""))


def open_url(url):
    """Open a page in the browser. True on success."""
    if not (url or "").strip():
        return False
    try:
        webbrowser.open(url)
        return True
    except Exception:
        return False


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


#: How many results are read at most, and how much of each is kept.
#:
#: Three and three hundred characters. What goes into the model's prompt
#: is paid for twice — in the time it takes to send and in the attention
#: it takes from the question itself — and a page of search results is
#: mostly the same sentence written four ways.
RESULTS = 3
SNIPPET = 300


def can_read() -> bool:
    """Is the package for reading results installed."""
    import importlib.util

    return importlib.util.find_spec("ddgs") is not None


def results(query, limit=RESULTS):
    """
    What the web says about this, as `[{title, body, href}]`.

    **Reading results is a different thing from opening a browser, and
    it is worth saying which is which.** Everything above hands a query
    to the person's browser and stops there: nothing of theirs comes
    back into the program. This fetches, and what comes back goes into
    a model's prompt — so the query leaves the machine to a search
    service, and somebody else's text arrives. That is a surface of its
    own (`T-23`) and it is why this is switched off until asked for.

    Empty on any failure. A search that did not happen is a question
    answered without it, which is the behaviour with the setting off —
    and far better than an answer that stops because a search engine
    was busy.
    """
    query = str(query or "").strip()
    if not query or not can_read():
        return []
    try:
        import logging

        from ddgs import DDGS

        # **The library is quietened, and that is not tidiness.** It
        # reports every backend it tries at INFO, with the whole address
        # — and the address carries the query. The query is what the
        # person asked, and the text of what a person said does not go
        # in the journal (`T-05`), whatever library happens to be
        # holding it at the time.
        logging.getLogger("ddgs").setLevel(logging.WARNING)
        logging.getLogger("primp").setLevel(logging.WARNING)

        found = DDGS().text(query, region="ru-ru", max_results=int(limit))
    except Exception as trouble:                        # noqa: BLE001
        log.warning("Поиск не удался: %s", trouble)
        return []

    out = []
    for row in found or []:
        title = str(row.get("title") or "").strip()
        body = str(row.get("body") or "").strip()[:SNIPPET]
        if title or body:
            out.append({"title": title, "body": body,
                        "href": str(row.get("href") or "").strip()})
    return out[:int(limit)]
