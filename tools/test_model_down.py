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
