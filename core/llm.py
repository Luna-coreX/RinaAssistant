"""
Ответы на свободные вопросы через локальную модель (Ollama).

Это последний шаг конвейера: если фразу не разобрал ни один обработчик,
вместо «Извини, я не поняла» на неё может ответить языковая модель.

Приватность: запрос уходит ТОЛЬКО на адрес из настройки llm_url (по умолчанию
localhost). Модель работает на компьютере пользователя, наружу ничего не
отправляется — именно поэтому выбран локальный Ollama, а не облачный сервис.

Зависимостей не добавляет: Ollama отвечает по HTTP, и хватает urllib.
"""

import json
import time
import urllib.error
import urllib.request

from core.i18n import t as tr


DEFAULT_URL = "http://localhost:11434"
DEFAULT_MODEL = "llama3.1:8b"
DEFAULT_TIMEOUT = 30

# Сколько последних реплик отдавать модели, чтобы разговор был связным.
# Больше — дороже и медленнее, а польза быстро выходит на полку.
CONTEXT_MESSAGES = 6

DEFAULT_PERSONA = (
    "Ты — Рина, голосовой ассистент на компьютере пользователя. "
    "Отвечай кратко и по делу: одно-два предложения, без списков и разметки — "
    "ответ будет произнесён вслух. Отвечай на языке собеседника. "
    "Если не знаешь ответа, честно скажи об этом."
)


class LLMError(Exception):
    """Модель недоступна или ответила ошибкой."""


def _settings():
    from core.settings_store import settings
    return settings


LOCAL_HOSTS = ("localhost", "127.0.0.1", "::1", "[::1]")
MAX_RESPONSE_BYTES = 4 * 1024 * 1024      # ответ модели заведомо меньше


def base_url():
    """
    Адрес сервера из настроек, если он выглядит адресом http(s).

    Адрес задаётся текстом, а по нему уходит переписка с моделью — поэтому
    непонятную строку не пробуем «как-нибудь» открыть, а возвращаемся
    к локальному серверу.
    """
    import urllib.parse

    url = str(_settings().get("llm_url", DEFAULT_URL) or DEFAULT_URL).strip()
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return DEFAULT_URL
    return url.rstrip("/")


def is_local_url(url=None):
    """Останется ли переписка на этом компьютере."""
    import urllib.parse

    parts = urllib.parse.urlsplit(url or base_url())
    return (parts.hostname or "").lower() in LOCAL_HOSTS


def is_enabled():
    return bool(_settings().get("llm_enabled", False))


def _request(path, payload=None, timeout=8):
    """Запрос к Ollama. Возвращает разобранный JSON."""
    url = base_url() + path
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            # ограничиваем чтение: сервер по этому адресу может быть каким угодно
            raw = resp.read(MAX_RESPONSE_BYTES)
            return json.loads(raw.decode("utf-8", errors="replace"))
    except urllib.error.URLError as e:
        raise LLMError(tr("Ollama не отвечает: ") + str(getattr(e, "reason", e)))
    except (ValueError, OSError) as e:
        raise LLMError(tr("Ошибка обращения к модели: ") + str(e))


# ---------------------------------------------------------------------------
# Состояние сервера
# ---------------------------------------------------------------------------
_status_cache = {"ts": 0.0, "models": None, "error": ""}
STATUS_TTL = 10          # секунд: не дёргать сервер на каждый чих


def models(force=False):
    """
    Список установленных моделей. Кэшируется, потому что настройки могут
    спрашивать его часто, а ответ меняется редко.
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
    """(доступна ли, текст для показа в настройках)."""
    found = models()
    if found:
        return True, tr("Ollama на связи, моделей: {count}", count=len(found))
    error = _status_cache.get("error")
    if error:
        return False, error
    return False, tr("Ollama отвечает, но моделей нет — установите модель")


def current_model():
    """Выбранная модель; если не выбрана — первая установленная."""
    chosen = str(_settings().get("llm_model", "") or "").strip()
    if chosen:
        return chosen
    found = models()
    return found[0] if found else DEFAULT_MODEL


def persona():
    text = str(_settings().get("llm_persona", "") or "").strip()
    return text or DEFAULT_PERSONA


# ---------------------------------------------------------------------------
# Вопрос модели
# ---------------------------------------------------------------------------
def _context_messages(history):
    """Последние реплики диалога в формате Ollama."""
    messages = []
    for entry in (history or [])[-CONTEXT_MESSAGES:]:
        role = "user" if entry.get("kind") == "user" else "assistant"
        text = str(entry.get("text", "")).strip()
        if text:
            messages.append({"role": role, "content": text})
    return messages


def ask(question, history=None):
    """
    Задаёт вопрос модели и возвращает ответ.
    Бросает LLMError, если модель недоступна или ответила пусто.
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
