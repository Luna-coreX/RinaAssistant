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
import time
import urllib.error
import urllib.request

from core.i18n import t as tr


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

    messages = [{"role": "system", "content": persona()}]
    messages += _context_messages(history)
    messages.append({"role": "user", "content": question})

    data = _request("/api/chat", payload={
        "model": current_model(),
        "messages": messages,
        "stream": False,
    }, timeout=max(5, min(timeout, 300)))

    answer = ((data.get("message") or {}).get("content") or "").strip()
    if not answer:
        raise LLMError(tr("Модель вернула пустой ответ"))
    return answer
