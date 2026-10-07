# -*- coding: utf-8 -*-
"""
The model that does not answer, and the model that is not on this machine.

Found 2026-10-03 from a person's log: «Спасибо», «Рина», «Рина!» each went
to the model, each waited thirty seconds for it, and each was then answered
«Извини, я не поняла команду». The model was `gemma4:31b-cloud` — served by
Ollama from its cloud, at localhost — and its connection had dropped.
Checked here, with the server substituted:

- a model that did not answer is left alone for a while, and the next
  question does not wait out the timeout again; another model is not;
- an answer clears the pause;
- a model Ollama serves from its cloud is known as such — by the server's
  own list and by its name — warned about when chosen, and written to the
  security journal when asked;
- after a model that did not answer, Rina says so instead of blaming the
  phrase.

To run:
    python tools/test_model_down.py
"""
import json
import logging
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

from console import use_utf8
from sandbox import isolate_storage, neutralise

use_utf8()
isolate_storage()

from core import llm

# The sandbox switches the model off by replacing `ask` — the very thing
# checked here — so it is kept and put back, as `test_persona` does. The
# server under it is substituted below.
_real_ask = llm.ask
neutralise()
llm.ask = _real_ask
from core.logging_setup import security_log
from core.settings_api import MemorySettings
from core.settings_schema import validate

fails = 0


def check(label, cond, detail=""):
    global fails
    if not cond:
        fails += 1
    print(("OK   " if cond else "FAIL "), label, detail)


values = {"llm_enabled": True, "llm_web": False, "llm_model": "local:7b",
          "llm_timeout": 30, "llm_url": "http://localhost:11434"}
asked = []
server = {"up": False}


def request(path, payload=None, timeout=None):
    asked.append((path, (payload or {}).get("model")))
    if not server["up"]:
        raise llm.LLMUnreachable("Ошибка обращения к модели: timed out")
    if path == "/api/tags":
        return {"models": [
            {"name": "local:7b"},
            {"name": "big:31b-cloud", "remote_host": "https://ollama.com"},
            {"name": "renamed:latest", "remote_host": "https://ollama.com"},
        ]}
    return {"message": {"content": "Ответ."}}


was = llm._request, llm._settings
llm._request = request
llm._settings = lambda: MemorySettings(values)
try:
    # -----------------------------------------------------------------------
    print("=== модель, которая не ответила, не ждут снова ===")
    try:
        llm.ask("Спасибо")
        check("первый вопрос — к модели, и она не ответила", False)
    except llm.LLMUnreachable:
        check("первый вопрос — к модели, и она не ответила", len(asked) == 1)

    started = time.perf_counter()
    try:
        llm.ask("Рина")
        check("второй — сразу, без похода к модели", False)
    except llm.LLMUnreachable:
        spent = time.perf_counter() - started
        check("второй — сразу, без похода к модели",
              len(asked) == 1 and spent < 0.5, f"| запросов {len(asked)}")
    check("и пауза — около минуты", 50 <= llm.resting() <= 60,
          f"| {llm.resting()} с")

    llm._rest["until"] = 0.0
    try:
        llm.ask("Рина!")
    except llm.LLMUnreachable:
        pass
    check("после паузы спрашивают снова, а не молчат навсегда", len(asked) == 2)
    check("второй провал подряд — пауза длиннее", llm.resting() > 60,
          f"| {llm.resting()} с")

    values["llm_model"] = "other:7b"
    server["up"] = True
    answer = llm.ask("Спасибо")
    check("другая модель — другая пауза: её спрашивают сразу",
          answer == "Ответ." and asked[-1] == ("/api/chat", "other:7b"),
          f"| {asked[-1:]}")
    values["llm_model"] = "local:7b"
    check("ответ снимает паузу", llm.resting() == 0 and llm.ask("Привет") == "Ответ.")

    # -----------------------------------------------------------------------
    print()
    print("=== облачная модель — не этот компьютер ===")
    for name, host in (("gemma4:31b-cloud", "ollama.com"),
                       ("qwen3-coder:cloud", "ollama.com"),
                       ("mistral:latest", ""), ("cloudy:7b", "")):
        check(f"«{name}» — {host or 'здесь'}", llm.cloud_host(name) == host,
              f"| {llm.cloud_host(name)!r}")
    llm.models(force=True)
    check("по списку самого сервера — и без «cloud» в имени",
          llm.cloud_host("renamed:latest") == "ollama.com")

    ok, code, said = validate("llm_model", "gemma4:31b-cloud")
    check("выбор облачной модели принят, но с предупреждением",
          ok and code == "llm.remote_address" and "ollama.com" in said, f"| {said}")
    ok, code, _ = validate("llm_model", "mistral:latest")
    check("а своей — без предупреждения", ok and code == "", f"| {code}")

    written = []

    class Catch(logging.Handler):
        def emit(self, record):
            written.append(record.getMessage())

    catch = Catch()
    security_log().addHandler(catch)
    try:
        values["llm_model"] = "big:31b-cloud"
        llm.ask("Как дела у погоды?")
    finally:
        security_log().removeHandler(catch)
        values["llm_model"] = "local:7b"
    check("вопрос облачной модели записан в журнал безопасности",
          any("big:31b-cloud" in line and "ollama.com" in line for line in written),
          f"| {written}")
    check("и сам вопрос туда не попал",
          not any("погоды" in line for line in written))
finally:
    llm._request, llm._settings = was
    llm._rest.update(key=None, failures=0, until=0.0)

# ---------------------------------------------------------------------------
print()
print("=== поставщики: Ollama, LM Studio, llama.cpp, OpenRouter (4.0b-E15) ===")
import urllib.error

from core.secrets import CORE, SecretStore


class Keys(dict):
    def __call__(self, method, payload):
        key = (payload.get("owner"), payload.get("name"))
        if method == "secrets.get":
            return {"found": key in self, "value": self.get(key, "")}
        if method == "secrets.set":
            self[key] = payload["value"]
            return {"ok": True}
        return {"deleted": int(self.pop(key, None) is not None)}


chosen = {"llm_enabled": True, "llm_web": False, "llm_model": "qwen",
          "llm_timeout": 30, "llm_url": ""}
llm._settings = lambda: MemorySettings(chosen)
for name, url in (("ollama", "http://localhost:11434"),
                  ("lmstudio", "http://localhost:1234"),
                  ("llamacpp", "http://127.0.0.1:8080"),
                  ("openrouter", "https://openrouter.ai/api")):
    chosen["llm_provider"] = name
    check(f"{name}: адрес по умолчанию {url}", llm.base_url() == url,
          f"| {llm.base_url()}")
chosen["llm_provider"] = "lmstudio"
chosen["llm_url"] = "http://localhost:11434"
check("адрес, оставшийся от другого поставщика, — не его",
      llm.base_url() == "http://localhost:1234", f"| {llm.base_url()}")
chosen["llm_url"] = "http://192.168.1.5:1234"
check("а свой адрес человека — его", llm.base_url() == "http://192.168.1.5:1234")
chosen["llm_provider"], chosen["llm_url"] = "openrouter", "http://evil.example"
check("у OpenRouter адрес один — ключ не уйдёт по чужому",
      llm.base_url() == "https://openrouter.ai/api")
chosen["llm_url"] = ""

sent = []
real_open = llm._open


class Answer:
    def __init__(self, body):
        self.body = json.dumps(body).encode()

    def read(self, limit=None):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def server(request, timeout=None):
    sent.append((request.full_url, dict(request.header_items()),
                 json.loads(request.data) if request.data else None))
    if request.full_url.endswith("/v1/models"):
        return Answer({"data": [{"id": "qwen"}, {"id": "llama"}]})
    if "evil" in request.full_url or request.get_header("Authorization") == "Bearer wrong":
        raise urllib.error.HTTPError(request.full_url, 401, "Unauthorized", {}, None)
    return Answer({"choices": [{"message": {"content": "Ответ OpenAI."}}]})


keys = Keys()
llm.secret_store = SecretStore(ask=keys)
llm._open = server
try:
    chosen["llm_provider"] = "lmstudio"
    check("LM Studio отвечает на диалекте OpenAI", llm.ask("Привет") == "Ответ OpenAI.")
    url, headers, body = sent[-1]
    check("и спрошен /v1/chat/completions с моделью и репликами",
          url == "http://localhost:1234/v1/chat/completions" and body["model"] == "qwen"
          and body["messages"][-1] == {"role": "user", "content": "Привет"}, f"| {url}")
    check("без ключа — без заголовка доступа", "Authorization" not in headers)
    check("список моделей — с /v1/models", llm.models(force=True) == ["qwen", "llama"])

    chosen["llm_provider"] = "openrouter"
    try:
        llm.ask("Привет")
        check("OpenRouter без ключа — отказ словами, без запроса", False)
    except llm.LLMError as refusal:
        check("OpenRouter без ключа — отказ словами, без запроса",
              "Ключ OpenRouter" in str(refusal) and not isinstance(
                  refusal, llm.LLMUnreachable), f"| {refusal}")
    keys[(CORE, llm.key_name("openrouter"))] = "sk-or-тайна"
    sent.clear()
    check("с ключом — отвечает", llm.ask("Привет") == "Ответ OpenAI.")
    url, headers, _body = sent[-1]
    check("ключ уходит заголовком, и только на openrouter.ai",
          url.startswith("https://openrouter.ai/api/") and
          headers.get("Authorization") == "Bearer sk-or-тайна", f"| {url}")
    keys[(CORE, llm.key_name("openrouter"))] = "wrong"
    try:
        llm.ask("Привет")
        check("неверный ключ — сказано про ключ, а не про сеть", False)
    except llm.LLMError as refusal:
        check("неверный ключ — сказано про ключ, а не про сеть",
              "ключ" in str(refusal) and not isinstance(refusal, llm.LLMUnreachable)
              and llm.resting() == 0, f"| {refusal}")

    ok, code, said = validate("llm_provider", "openrouter")
    check("выбор OpenRouter принят с предупреждением",
          ok and code == "llm.remote_address" and "openrouter.ai" in said)
    chosen["llm_provider"] = "ollama"
    sent.clear()
    keys[(CORE, llm.key_name("openrouter"))] = "sk-or-тайна"
    llm._request("/api/tags")
    check("Ollama ключ не получает никогда",
          "Authorization" not in sent[-1][1], f"| {sent[-1][1]}")

    # -- the key belongs to its service (audit 2026-10-07, M-2) -------------
    # One key for every provider sent OpenRouter's to whatever address the
    # LM Studio field held.
    chosen["llm_provider"] = "lmstudio"
    chosen["llm_url"] = "http://192.168.1.5:1234"
    sent.clear()
    llm.ask("Привет")
    check("ключ OpenRouter не уходит серверу LM Studio",
          "Authorization" not in sent[-1][1] and "sk-or" not in str(sent[-1][1]),
          f"| {sent[-1][1]}")

    keys[(CORE, llm.key_name("lmstudio"))] = "lm-своя"
    sent.clear()
    try:
        llm.ask("Привет")
    except llm.LLMError:
        pass
    check("свой ключ LM Studio по http в сеть не уходит",
          "Authorization" not in sent[-1][1], f"| {sent[-1][1]}")
    chosen["llm_url"] = "http://evil.example:1234"
    try:
        llm.ask("Привет")
        check("отказ без ключа назван: ключ придержан, а не неверен", False)
    except llm.LLMError as refusal:
        check("отказ без ключа назван: ключ придержан, а не неверен",
              "не отправлен" in str(refusal), f"| {refusal}")
    chosen["llm_url"] = "https://lm.example.org"
    sent.clear()
    llm.ask("Привет")
    check("по https — уходит", sent[-1][1].get("Authorization") == "Bearer lm-своя",
          f"| {sent[-1][1]}")
    chosen["llm_url"] = "http://localhost:1234"
    sent.clear()
    llm.ask("Привет")
    check("и на этот компьютер — уходит",
          sent[-1][1].get("Authorization") == "Bearer lm-своя")
finally:
    llm._open = real_open
    llm.secret_store = None
    llm._settings = was[1]
    llm._rest.update(key=None, failures=0, until=0.0)

# ---------------------------------------------------------------------------
print()
print("=== запрос с ключом не идёт за перенаправлением ===")
# On a real connection: `urllib` would carry `Authorization` to wherever a
# 3xx pointed, another host or plain http included.
import http.server
import threading

reached = []


class Elsewhere(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        reached.append(self.headers.get("Authorization"))
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"data": []}')

    do_POST = do_GET

    def log_message(self, *_args):
        pass


far = http.server.HTTPServer(("127.0.0.1", 0), Elsewhere)
threading.Thread(target=far.serve_forever, daemon=True).start()


class Sender(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(302)
        self.send_header("Location",
                         f"http://127.0.0.1:{far.server_address[1]}/v1/models")
        self.end_headers()

    do_POST = do_GET

    def log_message(self, *_args):
        pass


near = http.server.HTTPServer(("127.0.0.1", 0), Sender)
threading.Thread(target=near.serve_forever, daemon=True).start()

keys = Keys()
keys[(CORE, llm.key_name("llamacpp"))] = "llama-secret"
llm.secret_store = SecretStore(ask=keys)
llm._settings = lambda: MemorySettings({
    "llm_enabled": True, "llm_web": False, "llm_model": "qwen",
    "llm_timeout": 5, "llm_provider": "llamacpp",
    "llm_url": f"http://127.0.0.1:{near.server_address[1]}"})
try:
    llm._request("/v1/models")
    check("перенаправление с ключом — отказ", False)
except llm.LLMError as refusal:
    check("перенаправление с ключом — отказ, и назван",
          "перенаправ" in str(refusal), f"| {refusal}")
check("и до второго сервера ключ не дошёл", reached == [], f"| {reached}")
llm.secret_store = None
llm._settings = was[1]
llm._rest.update(key=None, failures=0, until=0.0)
near.shutdown()
far.shutdown()

# ---------------------------------------------------------------------------
print()
print("=== молчание модели названо, а не свалено на фразу ===")
from core.engine import RinaEngine

engine = RinaEngine(settings=MemorySettings({
    "stt_engine": "disabled", "custom_commands": [], "reminders": [],
    "history": [], "web_search_fallback": False,
}))
heard = []
engine.say = lambda text, sound="response": heard.append(text)
engine._fallback_reply("Спасибо", "typed", model_down=True)
check("модель не ответила — так и сказано",
      heard and heard[-1].startswith("Модель сейчас не отвечает"), f"| {heard}")
engine._fallback_reply("абракадабра", "typed")
check("а непонятая фраза — по-прежнему непонятая",
      heard[-1] == "Извини, я не поняла команду.", f"| {heard[-1:]}")

print()
print("ИТОГО ошибок:", fails)
sys.exit(1 if fails else 0)
