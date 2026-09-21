# -*- coding: utf-8 -*-
"""
4.0b-E13: the model looks things up, and only when it asks to.

**Nothing here touches the network.** The search is replaced, because
what is being checked is not whether DuckDuckGo answers — that is
somebody else's service and a check that depends on it measures their
afternoon — but the three decisions around it.

*It asks, we do not guess.* A model that needs a search says so in one
fixed line. Recognising "I don't know" in free text would mean
searching because an answer happened to contain the word.

*One search, not a conversation.* The second pass is told nothing
about searching, so a model that likes the word cannot loop.

*Nothing found is not a failure.* The question goes back without
results and is answered as it would have been with the setting off.

And the surface `T-23` describes: the query goes out, somebody else's
text comes in, and neither happens with the switch off.
"""
import os
import sys

sys.path.insert(0, r"C:\DevStation\PCDev\DesktopApps\RinaAssistant")
sys.path.insert(0, os.path.join(
    r"C:\DevStation\PCDev\DesktopApps\RinaAssistant", "tools"))

from sandbox import neutralise

# The real `ask` is kept before the sandbox replaces it.
#
# The sandbox stops the model being reached, and rightly: a check that
# talks to somebody's Ollama measures their afternoon. But this check
# is **about** `ask` — about which pass gets told what — so it keeps
# the real one and substitutes the layer below instead, the single
# call that goes to the network. Nothing here reaches further than
# that, and the substitution is proved by the model stub counting the
# passes.
from core import llm as _llm

_real_ask = _llm.ask
neutralise(storage=False)
_llm.ask = _real_ask

from console import use_utf8
from core import llm
from core.settings_api import MemorySettings
from voice import websearch

use_utf8()

fails = 0


def check(label, cond, detail=""):
    global fails
    if not cond:
        fails += 1
    print(("OK   " if cond else "FAIL "), label, detail)


class Model:
    """A model that says what it is told to say, and remembers the asking."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.asked = []          # the system prompt of every pass

    def __call__(self, path, payload=None, timeout=None):
        told = [m for m in payload["messages"] if m["role"] == "system"]
        self.asked.append(told[0]["content"] if told else "")
        answer = self.replies.pop(0) if self.replies else "…"
        return {"message": {"content": answer}}


def run(replies, found=(), web=True, question="что сегодня в мире"):
    """Ask, with the network replaced on both sides."""
    model = Model(*replies)
    searched = []

    def instead(query, limit=3):
        searched.append(query)
        return list(found)

    was_request, was_results = llm._request, websearch.results
    was_settings = llm._settings
    llm._request = model
    websearch.results = instead
    llm._settings = lambda: MemorySettings({
        "llm_enabled": True, "llm_web": web, "llm_model": "m",
        "llm_timeout": 30,
    })
    try:
        return model, searched, llm.ask(question)
    finally:
        llm._request, websearch.results = was_request, was_results
        llm._settings = was_settings


print("=== модель просит поиск сама ===")
model, searched, answer = run(
    ["ПОИСК: новости за сегодня", "Вот что нашлось: небо голубое."],
    found=[{"title": "Небо", "body": "Оно голубое.", "href": "x"}])
check("поиск был, и по её запросу",
      searched == ["новости за сегодня"], f"| {searched}")
check("ответ пришёл со второго прохода",
      "небо голубое" in answer.lower(), f"| {answer}")
check("модель спрашивали дважды", len(model.asked) == 2,
      f"| {len(model.asked)}")
# The whole point of a marker instead of a phrase.
check("в первый раз ей предложили искать",
      "ПОИСК:" in model.asked[0], f"| {model.asked[0][:60]}")
check("во второй — уже нет",
      "ПОИСК:" not in model.asked[1],
      "| второй проход знает про поиск — модель может ходить по кругу")
check("и найденное ей передали",
      "Оно голубое" in model.asked[1], f"| {model.asked[1][:80]}")

print()
print("=== находкам сказано, что они ответ ===")
# **Handed over silently, the findings were ignored.** Measured on
# the model this was found on: asked «какая погода в Хабаровске», it asked for a
# search, was given three forecasts for that day and that city, and
# answered «у меня нет доступа к актуальным данным в реальном времени».
# The persona pulls that way too — it says to admit honestly when she
# does not know — and nothing on the second pass said that she now does.
model, searched, answer = run(
    ["ПОИСК: погода в Хабаровске", "Плюс двенадцать."],
    found=[{"title": "Погода", "body": "Плюс двенадцать.", "href": "x"}])
told = model.asked[1]
check("сказано отвечать по найденному",
      "Отвечай по найденному" in told, "| указания нет")
check("и не отговариваться отсутствием доступа",
      "в реальном времени" in told, "| про доступ не сказано")
# The opposite failure is worse: told only to answer from the findings,
# a model that was handed links without numbers would invent numbers.
check("но если ответа в находках нет — сказать прямо",
      "чего не хватает" in told, "| оговорки нет")
check("сами находки на месте",
      "Плюс двенадцать" in told, "| находок в промпте нет")

print()
print("=== не просила — не искали ===")
model, searched, answer = run(["Канберра."])
check("поиска не было", searched == [], f"| {searched}")
check("ответ её собственный", answer == "Канберра.", f"| {answer}")
check("прохода хватило одного", len(model.asked) == 1, f"| {len(model.asked)}")

print()
print("=== выключатель выключает ===")
model, searched, answer = run(["ПОИСК: что угодно"], web=False)
check("с выключенной настройкой не ищем", searched == [], f"| {searched}")
check("и не предлагаем искать",
      "ПОИСК:" not in model.asked[0], f"| {model.asked[0][:60]}")
# The line is then just an answer: odd, but hers, and saying it is
# better than swallowing it.
check("ответ не пропал", answer.startswith("ПОИСК:"), f"| {answer}")

print()
print("=== ничего не нашлось — не отказ ===")
model, searched, answer = run(
    ["ПОИСК: пустота", "Не нашла, но вот что знаю сама."], found=[])
check("искали", searched == ["пустота"], f"| {searched}")
check("и всё равно ответили",
      "знаю сама" in answer, f"| {answer}")
check("второй проход прошёл без находок",
      "Найдено в интернете" not in model.asked[1],
      f"| {model.asked[1][:80]}")

print()
print("=== модели говорят, какое сегодня число ===")
# The half that was missing, and the reason «что было с MR-очками в
# 2026» came back as "I have no information about 2026, my data ends
# earlier". That is true, polite, and the opposite of asking to be
# told: the model was not refusing to search, it did not know that
# 2026 had happened.
import time as time_mod

told = llm.may_search()
now = time_mod.localtime()
check("названо сегодняшнее число",
      str(now.tm_mday) in told and str(now.tm_year) in told,
      f"| {told.splitlines()[0][:70]}")
check("и месяц словом, а не номером",
      llm.MONTHS[now.tm_mon - 1] in told,
      f"| ждали «{llm.MONTHS[now.tm_mon - 1]}»")
# Said outright, because "I do not know" was the answer it kept giving
# instead of asking.
check("сказано не отвечать «не знаю»", "не знаю" in told, f"| {told[-160:]}")
check("и не ссылаться на устаревшие данные",
      "устарели" in told or "ограничения" in told, f"| {told[:90]}")

print()
print("=== разметка просьбы ===")
for line, want in (("ПОИСК: погода в Москве", "погода в Москве"),
                   ("  ПОИСК:   погода  ", "погода"),
                   ("Я не знаю, но думаю, что это ПОИСК: неважно", None),
                   ("Не знаю.", None),
                   ("", None)):
    found = llm.WANTS_SEARCH.match(line)
    got = found.group(1) if found else None
    check(f"«{line.strip()[:34]}» -> {want}", got == want, f"| {got}")

print()
print("=== без пакета поиска ничего не ломается ===")
# The package is installed on consent, so its absence is the ordinary
# state and must answer "nothing found" rather than raise.
was = websearch.can_read
websearch.can_read = lambda: False
try:
    check("results() возвращает пусто",
          websearch.results("что угодно") == [], "| и не бросает")
finally:
    websearch.can_read = was

print()
print("ИТОГО ошибок:", fails)
sys.exit(1 if fails else 0)
