"""
Answers to free-form questions through a local model (Ollama).

This is the pipeline's last step: if a phrase was parsed by no handler, then
instead of "Sorry, I did not understand" a language model may answer it.

Privacy: the request goes ONLY to the address in the llm_url setting
(localhost by default). The model runs on the user's computer, nothing is
sent outside — which is exactly why a local Ollama was chosen rather than a
cloud service.

It adds no dependencies: Ollama answers over HTTP, and urllib is enough.
"""

import http.client
import json
import re
import time
import urllib.error
import urllib.request

from core.i18n import t as tr
from core.logging_setup import get_logger, safe

log = get_logger("llm")


DEFAULT_URL = "http://localhost:11434"
DEFAULT_MODEL = "llama3.1:8b"
DEFAULT_TIMEOUT = 30

# How many recent lines to give the model, so the conversation is coherent.
# More is dearer and slower, and the benefit quickly plateaus.
CONTEXT_MESSAGES = 6

DEFAULT_PERSONA = (
    "Ты — Рина, голосовой ассистент на компьютере пользователя. "
    "Отвечай кратко и по делу: одно-два предложения, без списков и разметки — "
    "ответ будет произнесён вслух. Отвечай на языке собеседника. "
    "Если не знаешь ответа, честно скажи об этом."
)


class LLMError(Exception):
    """The model is unavailable or answered with an error."""


def _settings():
    from core.settings_store import settings
    return settings


LOCAL_HOSTS = ("localhost", "127.0.0.1", "::1", "[::1]")
MAX_RESPONSE_BYTES = 4 * 1024 * 1024      # a model's answer is knowingly smaller


def base_url():
    """
    The server's address from the settings, if it looks like an http(s)
    address.

    The address is given as text, and correspondence with the model goes to
    it — so we do not try to open an unintelligible string "somehow" but
    fall back to the local server.
    """
    import urllib.parse

    url = str(_settings().get("llm_url", DEFAULT_URL) or DEFAULT_URL).strip()
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return DEFAULT_URL
    return url.rstrip("/")


def is_local_url(url=None):
    """Will the correspondence stay on this computer."""
    import urllib.parse

    parts = urllib.parse.urlsplit(url or base_url())
    return (parts.hostname or "").lower() in LOCAL_HOSTS


def is_enabled():
    return bool(_settings().get("llm_enabled", False))


def _request(path, payload=None, timeout=8):
    """A request to Ollama. Returns the parsed JSON."""
    url = base_url() + path
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if not is_local_url(url):
        # the correspondence is leaving this computer — that is a security event
        from core.logging_setup import security_log
        security_log().warning("Запрос к модели по нелокальному адресу: %s",
                               base_url())
    req = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            # we limit the read: the server at this address may be anything at all
            raw = resp.read(MAX_RESPONSE_BYTES)
            return json.loads(raw.decode("utf-8", errors="replace"))
    except urllib.error.URLError as e:
        raise LLMError(tr("Ollama не отвечает: ") + str(getattr(e, "reason", e)))
    except (ValueError, OSError, http.client.HTTPException) as e:
        # HTTPException (a truncated response, broken chunking, too long a
        # header line) does not inherit from OSError and used to fly out
        # past us: the "Check the connection" button stayed in the checking
        # state forever
        raise LLMError(tr("Ошибка обращения к модели: ") + str(e))


# ---------------------------------------------------------------------------
# The server's state
# ---------------------------------------------------------------------------
_status_cache = {"ts": 0.0, "models": None, "error": ""}
STATUS_TTL = 10          # seconds: do not pester the server over every trifle


def models(force=False):
    """
    The list of installed models. Cached, because the settings may ask for
    it often while the answer changes rarely.
    """
    now = time.time()
    if not force and _status_cache["models"] is not None \
            and now - _status_cache["ts"] < STATUS_TTL:
        return list(_status_cache["models"])

    try:
        data = _request("/api/tags", timeout=5)
        found = [str(m.get("name", "")) for m in (data.get("models") or [])]
        found = [m for m in found if m]
        _status_cache.update({"ts": now, "models": found, "error": ""})
        return list(found)
    except LLMError as e:
        _status_cache.update({"ts": now, "models": [], "error": str(e)})
        return []


def status():
    """(is it available, the text to show in the settings)."""
    found = models()
    if found:
        return True, tr("Ollama на связи, моделей: {count}", count=len(found))
    error = _status_cache.get("error")
    if error:
        return False, error
    return False, tr("Ollama отвечает, но моделей нет — установите модель")


def current_model():
    """The chosen model; if none is chosen, the first installed one."""
    chosen = str(_settings().get("llm_model", "") or "").strip()
    if chosen:
        return chosen
    found = models()
    return found[0] if found else DEFAULT_MODEL


def persona():
    text = str(_settings().get("llm_persona", "") or "").strip()
    return text or DEFAULT_PERSONA


# ---------------------------------------------------------------------------
# A question to the model
# ---------------------------------------------------------------------------
def _context_messages(history):
    """The dialogue's recent lines in Ollama's format."""
    messages = []
    for entry in (history or [])[-CONTEXT_MESSAGES:]:
        role = "user" if entry.get("kind") == "user" else "assistant"
        text = str(entry.get("text", "")).strip()
        if text:
            messages.append({"role": role, "content": text})
    return messages


#: What the model says when it wants to look something up.
#:
#: A line of its own rather than a phrase to be recognised. "Answer
#: `ПОИСК: <запрос>` and nothing else" is a thing a model either did or
#: did not do; "I do not know, this needs checking" is a thing somebody
#: has to guess at, and guessing at free text is how a program comes to
#: search because an answer happened to contain the word "unknown".
WANTS_SEARCH = re.compile(r"^\s*ПОИСК:\s*(.+?)\s*$")

#: Months, for saying today's date to the model.
#:
#: A table rather than `strftime("%B")`: that one answers in whatever
#: language the machine's locale happens to be, and the model is being
#: spoken to in Russian.
MONTHS = ("января", "февраля", "марта", "апреля", "мая", "июня", "июля",
          "августа", "сентября", "октября", "ноября", "декабря")


def may_search():
    """What the model is told when it is allowed to look things up.

    **The date comes first, and it is the half that was missing.** The
    first edition only offered the search, and a model whose training
    stopped in 2024 answered «что было с MR-очками в 2026» with "I do
    not have information about 2026, my data ends earlier" — which is
    true, polite, and the exact opposite of asking to be told. It was
    not refusing to search; it did not know that 2026 had happened.

    So it is told the date, and told plainly that its own knowledge is
    out of date past it. Then "I do not know this" stops being a
    conclusion and becomes a reason.

    Measured against the model this was found on: with the offer alone,
    one of the two questions asked for a search; with the date and the
    instruction not to answer "I do not know", both did, while "как
    дела" and "сколько будет два плюс два" still went unsearched.
    """
    today = time.localtime()
    return (
        "Сегодня %d %s %d года. Твои собственные знания устарели: всё, "
        "что случилось позже них, ты узнаёшь только поиском.\n"
        "Ты умеешь искать в интернете. Если сведений не хватает — "
        "свежих, местных или просто тебе неизвестных — не отвечай «не "
        "знаю» и не говори про ограничения своих данных: вместо этого "
        "ответь ровно одной строкой ПОИСК: <что искать> — и ничем "
        "больше. Искать буду я и верну тебе найденное."
        % (today.tm_mday, MONTHS[today.tm_mon - 1], today.tm_year)
    )


def _searched(query):
    """What the web says, as lines for the prompt. Empty if nothing.

    **The findings come with an instruction, and without it they were
    ignored.** Handing them over silently is not enough: asked «какая
    погода в Хабаровске», the model asked for a search, got three
    forecasts for that day and that city, and answered «у меня нет
    доступа к актуальным данным в реальном времени». The persona is
    part of why — it says to admit honestly when she does not know, and
    on the second pass nothing said that she now does.

    So it is said. Along with the escape, because the opposite failure
    is worse: if the answer really is not among the findings, saying
    what is missing beats inventing it.
    """
    from voice import websearch

    found = websearch.results(query)
    if not found:
        return ""
    lines = [
        "Ты просила поискать — вот что нашлось. Отвечай по найденному: "
        "это и есть те свежие сведения, которых тебе не хватало. Не "
        "отвечай «не знаю» и не говори, что у тебя нет доступа к данным "
        "в реальном времени: данные перед тобой. Если ответа в найденном "
        "всё-таки нет, скажи прямо, чего не хватает.",
        "Найдено в интернете по запросу «%s»:" % query,
    ]
    for at, one in enumerate(found, 1):
        lines.append("%d. %s — %s" % (at, one["title"], one["body"]))
    return "\n".join(lines)


def ask(question, history=None):
    """
    Asks the model a question and returns the answer.
    Raises LLMError if the model is unavailable or answered with nothing.
    """
    question = str(question or "").strip()
    if not question:
        raise LLMError(tr("Пустой вопрос"))

    try:
        timeout = int(_settings().get("llm_timeout", DEFAULT_TIMEOUT))
    except (TypeError, ValueError):
        timeout = DEFAULT_TIMEOUT

    wants_web = bool(_settings().get("llm_web", False))

    def once(extra=""):
        told = persona()
        if extra:
            told = (told + "\n\n" + extra) if told else extra
        messages = [{"role": "system", "content": told}]
        messages += _context_messages(history)
        messages.append({"role": "user", "content": question})
        data = _request("/api/chat", payload={
            "model": current_model(),
            "messages": messages,
            "stream": False,
        }, timeout=max(5, min(timeout, 300)))
        return ((data.get("message") or {}).get("content") or "").strip()

    answer = once(may_search() if wants_web else "")

    # **The model decides, and it gets one search — not a conversation.**
    #
    # Asking it first and searching only when it says it needs to is
    # what keeps "как дела" from costing two seconds and a query to
    # somebody else's service. What it must not become is a loop: the
    # second pass is told nothing about searching, so a model that
    # likes the word cannot spend an afternoon on it.
    #
    # A search that found nothing is not reported as a failure. The
    # question goes back without results and is answered as it would
    # have been with the setting off — which is a worse answer, and a
    # better one than silence.
    if wants_web:
        found = WANTS_SEARCH.match(answer)
        if found:
            query = found.group(1)
            log.info("Модель попросила поиск: %s", safe(query))
            answer = once(_searched(query))

    if not answer:
        raise LLMError(tr("Модель вернула пустой ответ"))
    return answer
