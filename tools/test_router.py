# -*- coding: utf-8 -*-
"""B02: the router is a pure function. Checked without the application."""
import os
import sys

sys.path.insert(0, r"C:\DevStation\PCDev\DesktopApps\RinaAssistant")
sys.path.insert(0, os.path.join(
    r"C:\DevStation\PCDev\DesktopApps\RinaAssistant", "tools"))

# The checks do not touch the machine (`4.0-I04`).
#
# Under the interpreter the core actually runs on, `sounddevice` is
# installed — so every answer here played a real cue through the real
# speakers, sixty-nine of them across the suite, and two tests brought
# the process down on the way out. The group "машина" exists precisely
# so that the ordinary run touches nothing; this check belongs to the
# ordinary run.
#
# Storage is left alone: these tests bring their own, and moving it
# would change what they measure rather than what they touch.
from sandbox import neutralise

neutralise(storage=False)

from core.dialog import Question
from core.router import route, RouterContext
from voice.app_index import AppEntry

fails = 0


def check(label, cond, detail=""):
    global fails
    if not cond:
        fails += 1
    print(("OK   " if cond else "FAIL "), label, detail)


APPS = [
    AppEntry("Telegram Desktop", r"C:\Apps\Telegram.exe", "file", "start_menu"),
    AppEntry("Google Chrome", r"C:\Chrome\chrome.exe", "file", "start_menu"),
    AppEntry("Visual Studio Code", r"C:\VSCode\Code.exe", "file", "start_menu"),
    AppEntry("Visual Studio 2022", r"C:\VS\devenv.exe", "file", "start_menu"),
]
ctx = RouterContext(apps=APPS)


print("=== чистота ===")
check("Qt не загружен", "PySide6" not in sys.modules)
check("настройки не загружены", "core.settings_store" not in sys.modules)
check("ядро не загружено", "core.engine" not in sys.modules)

before = route("запусти телеграм", ctx)
after = route("запусти телеграм", ctx)
check("повторный вызов даёт то же", before == after, f"| {before}")

print()
print("=== namespace намерений ===")
cases = [
    ("запусти телеграм", "app.launch"),
    ("поставь таймер на 10 минут", "reminder.create"),
    ("какие таймеры", "reminder.list"),
    ("отмени все таймеры", "reminder.cancel"),
    ("громче", "system.action"),
    ("выключи компьютер", "system.confirm"),
    ("посчитай 15*12", "calc"),
    ("посчитай 10/0", "calc.zero_division"),
    ("найди рецепт борща", "websearch"),
    ("как тебя зовут", "builtin.answer"),
    ("столица австралии", "fallback.search"),
    ("", "silence"),
]
for phrase, expected in cases:
    got = route(phrase, ctx)
    check(f"{phrase!r:32} -> {expected}", got.name == expected, f"| {got}")

print()
print("=== контекст решает, а не глобальное состояние ===")
quiet = RouterContext(apps=APPS, web_fallback=False)
check("без запасного поиска — отказ",
      route("столица австралии", quiet).name == "fallback.none")

llm = RouterContext(apps=APPS, llm_enabled=True)
answer = route("столица австралии", llm)
check("с моделью — намерение модели", answer.name == "llm.answer")
check("уверенность ниже единицы", answer.confidence < 1.0,
      f"| {answer.confidence}")

always = RouterContext(apps=APPS, unbidden=True)
check("при открытом микрофоне поиска нет",
      route("столица австралии", always).name == "fallback.none")

full = RouterContext(apps=APPS, reminders_active=3)
check("непустой список видно", route("какие таймеры", full).arg("empty") is False)

print()
print("=== слово активации ===")
wake = RouterContext(apps=APPS, require_wake=True)
check("без активации — молчание",
      route("запусти телеграм", wake).name == "silence")
check("с активацией — команда",
      route("Рина запусти телеграм", wake).name == "app.launch")
check("голое слово активации",
      route("Рина", wake).name == "ask.wake")
wake_always = RouterContext(apps=APPS, require_wake=True, unbidden=True)
check("голое слово при открытом микрофоне — молчание",
      route("Рина", wake_always).name == "silence")

print()
print("=== ответ на вопрос ===")
confirm = RouterContext(
    apps=APPS, pending=Question.confirm_action("shutdown").to_dict())
check("согласие", route("да", confirm).name == "system.action")
check("отказ", route("нет", confirm).name == "cancelled")
check("«нет, давай» — отказ (поведение 3.1.0)",
      route("нет, давай", confirm).name == "cancelled")
check("невнятный ответ — не ответ",
      route("какая погода", confirm).name != "system.action")

# The question always arrives serialised: the router works with state that
# can be written to a file and sent over the protocol (4.0-B03).
choose = RouterContext(apps=APPS, pending=Question.choose_app(
    APPS[2:4], query="visual studio").to_dict())
picked = route("второй", choose)
check("выбор порядковым", picked.name == "app.launch"
      and picked.arg("app") == "Visual Studio 2022", f"| {picked}")
check("выбор именем",
      route("visual studio code", choose).arg("app") == "Visual Studio Code")
check("отмена выбора", route("отмена", choose).name == "cancelled")

print()
print("=== то же самое ядро и собирает ===")
# **Both checks above were green while both rules were dead.** They asked
# `source="always"`, and that name is passed by the 3.1.0 path where the
# core opened the microphone itself. Since `4.0-G` the sound comes from
# the shell and calls itself `voice` in either mode — so "do not search
# the internet for chance speech" had never once fired in the running
# program, and an open microphone answered a web search to every noise in
# the room. A person met that; no check could, because the checks built a
# context the program does not build.
#
# So the context is taken from the core here, not written out by hand.
# Two objects agreeing on a rule is worth nothing if only one of them is
# ever asked.
from core.engine import RinaEngine
from core.settings_api import MemorySettings

brain = RinaEngine(settings=MemorySettings({
    "stt_engine": "disabled", "custom_commands": [], "reminders": [],
    "history": [], "web_search_fallback": True,
}))
brain.ears_outside = True

quiet_ctx = brain._router_context("voice", require_wake=False)
check("при закрытом микрофоне контекст не «непрошеный»",
      quiet_ctx.unbidden is False, f"| {quiet_ctx.unbidden}")

brain._always_listen = True
open_ctx = brain._router_context("voice", require_wake=True)
check("при открытом — «непрошеный», хотя источник тот же",
      open_ctx.unbidden is True and open_ctx.source == "voice",
      f"| unbidden={open_ctx.unbidden}, source={open_ctx.source!r}")
# With the wake word, or the phrase never reaches the tail: without it
# the wake stage answers `silence`, and the check would be green about
# the wrong rule.
check("и поиска по такому контексту не будет даже при обращении",
      route("Рина, столица австралии", open_ctx).name == "fallback.none",
      f"| {route('Рина, столица австралии', open_ctx).name}")

print()
print("=== разговор: слово активации говорится один раз ===")
# The complaint that started `4.0b-E06`: "the activation word has to be
# said before every phrase". A person says a name once and then talks;
# saying it again before each sentence is addressing a machine, not
# speaking to somebody.
#
# The boundary the plan sets against it: an open conversation is an open
# ear — the same surface as `T-19` — so it must be **finite**, **visible**
# and **close itself**. All three are asked here; the visible part is
# asked of the shell in `--check-overlays`.
import time as _time

talker = RinaEngine(settings=MemorySettings({
    "stt_engine": "disabled", "custom_commands": [], "reminders": [],
    "history": [], "web_search_fallback": True,
}))
talker.ears_outside = True
talker._always_listen = True

said = []
talker.bus.on("listening.conversation", lambda data: said.append(dict(data)))

check("в покое разговора нет", not talker.talking())
ctx_shut = talker._router_context("voice", require_wake=True)
check("и слово активации спрашивается",
      route("что ты умеешь", ctx_shut).name == "silence",
      "| без имени и без разговора — молчание")

talker.handle_command("Рина, что ты умеешь", require_wake=True,
                      source="voice")
check("после обращения разговор открыт", talker.talking())
check("и об этом сказано наружу",
      bool(said) and said[0].get("open") is True,
      f"| {said}")

ctx_open = talker._router_context("voice", require_wake=True)
check("внутри разговора имя уже не нужно",
      route("что ты умеешь", ctx_open).name == "builtin.answer",
      f"| {route('что ты умеешь', ctx_open).name}")

# Finite. The window is a length of time, not a mood: it is asked here by
# moving the deadline into the past rather than by waiting fifteen
# seconds, because a check that sleeps for its subject is a check nobody
# runs.
talker._talking_until = _time.monotonic() - 0.01
check("время вышло — разговор закрыт", not talker.talking())
ctx_shut = talker._router_context("voice", require_wake=True)
check("и имя спрашивается снова",
      route("что ты умеешь", ctx_shut).name == "silence")

# Closes itself, out loud. The timer is what does it in life; here it is
# called directly, because what is being checked is that closing is
# announced, not that `threading.Timer` works.
talker.handle_command("Рина, что ты умеешь", require_wake=True,
                      source="voice")
said.clear()
talker._talking_until = _time.monotonic() - 0.01
talker._talk_ran_out()
check("закрылся сам — и сказал об этом",
      bool(said) and said[-1].get("open") is False,
      f"| {said}")

# And it does not grow for ever. Extended turn by turn without a ceiling
# the word would stay optional for an afternoon — the third part of the
# boundary, and the easiest of the three to lose.
talker.handle_command("Рина, что ты умеешь", require_wake=True,
                      source="voice")
talker._talking_since = _time.monotonic() - RinaEngine.TALK_LIMIT + 3
talker.handle_command("что ты умеешь", require_wake=True, source="voice")
left = talker._talking_until - _time.monotonic()
check("у долгого разговора есть потолок", left <= 3.5,
      f"| осталось {left:.1f} с при окне {RinaEngine.TALK_WINDOW:.0f}")

# A typed line opens nothing: it needs no wake word anyway, and opening
# the ear because somebody typed would be answering a question nobody
# asked.
quiet = RinaEngine(settings=MemorySettings({
    "stt_engine": "disabled", "custom_commands": [], "reminders": [],
    "history": [],
}))
quiet.handle_command("что ты умеешь", source="typed")
check("напечатанное разговора не открывает", not quiet.talking())

print()
print("=== обращение — это ещё не команда, но уже разговор ===")
# Out of six ordinary ways of addressing her, one was answered. The
# rest went to the end of the parse and got "Извини, я не поняла
# команду" — and with "always listening" off, a web search for the word
# "привет". The target model of behaviour ends on «Спасибо, Рина» —
# «Всегда рада помочь»; an assistant that answers "не поняла" to a
# greeting does not enter that conversation at all.
for text, want in [
    ("привет", "builtin.answer"),
    ("здравствуй", "builtin.answer"),
    ("спасибо", "builtin.answer"),
    ("пока", "builtin.answer"),
    ("как дела", "builtin.answer"),
    ("ты кто", "builtin.answer"),
    ("что ты умеешь", "builtin.answer"),
    # And it takes nothing that belongs to somebody else: the stages
    # that carry a real errand run before this one, and have to keep
    # running first.
    ("какие дела", "todo.list"),
    ("напомни через 5 минут сказать привет соседу", "reminder.create"),
    ("запиши позвонить и сказать спасибо", "todo.add"),
    ("найди как дела у рынка акций", "websearch"),
]:
    got = route(text, RouterContext()).name
    check(f"{text}", got == want, "" if got == want else f"| {got} вместо {want}")

print()
print("=== делить — это делить, а не умножать ===")
# **Answered confidently and wrongly.** «5 делить на 0» came out as
# «Получается 0»: the bare verb was missing from the table, so it was
# dropped as filler, «на» met the rule that makes it multiplication,
# and the expression became `5 * 0`. A calculator that gives the wrong
# operation without a word is worse than one that says it did not
# understand.
from voice import calculator

sums = [
    ("сколько будет 5 делить на 0", "calc.zero_division", None),
    ("сколько будет 10 делить на 2", "calc", "5"),
    ("сколько будет 12 дели на 4", "calc", "3"),
    ("сколько будет 100 разделить на 5", "calc", "20"),
    ("сколько будет 9 подели на 3", "calc", "3"),
    # And multiplication is still multiplication: the rule that turns
    # «на» into a product is what this broke against, and it has to
    # survive the fix.
    ("сколько будет 7 на 6", "calc", "42"),
    ("посчитай 8 умножить на 3", "calc", "24"),
]
for text, want_name, want_result in sums:
    got = calculator.classify(text)
    name = got[0] if got else "—"
    result = (got[1] or {}).get("result") if got else None
    check(f"{text}",
          name == want_name and (want_result is None or result == want_result),
          f"| {name} {result}")

print()
print("=== просьба напомнить без времени не идёт в интернет ===")
# «напомни позвонить маме» — an ordinary thing to say — used to reach
# the search stage and be sent to a search engine: useless as an answer,
# and for somebody's own errand worse than useless as an action.
for text, want in [
    ("напомни позвонить маме", "reminder.no_time"),
    ("напомни", "reminder.no_time"),
    ("поставь будильник", "reminder.no_time"),
    ("напомни через 0 секунд проверить", "reminder.no_time"),
    ("напомни через 5 минут позвонить", "reminder.create"),
    # But a phrase that merely contains the word is a phrase, not a
    # request: the first cut of this caught it and answered "Не поняла,
    # когда напомнить" to a question about psychology.
    ("что такое напоминание в психологии", "fallback.search"),
    ("расскажи про будильники", "fallback.search"),
]:
    got = route(text, RouterContext()).name
    check(f"{text}", got == want, "" if got == want else f"| {got} вместо {want}")

print()
print("=== окно разговора не съедается её же ответом ===")
# **The defect that made the whole feature unusable.** The window opens
# when the phrase is understood, and then Rina answers: a second or two
# before the first sound, nine seconds of speech. By the time a person
# can say the next thing without her name, fifteen seconds are gone.
# Straight from the journal, three times over — and note the apostrophe
# left out of this sentence on purpose: a stray one pairs with the next
# quote mark and hides the Russian below from the language check.

#
#     `13:11:55  Команда (voice): 'что ты умеешь?'`
#     `13:12:25  'Хорошо, запустите им.'`
#     `13:12:26  Расслышано, но не мне (wake)`
#
# The window belongs to whoever is listening, so it begins when they
# can speak — after she stops.
import time as _clock

from core.engine import RinaEngine
from core.settings_api import MemorySettings

talker = RinaEngine(settings=MemorySettings({
    "custom_commands": [], "reminders": [], "history": [], "todo": [],
}))
talker._open_talk()
now = _clock.monotonic()
check("окно открыто на пятнадцать секунд",
      talker.talking(now + 14) and not talker.talking(now + 16),
      f"| {round(talker._talking_until - now, 1)} с")

talker.talk_after_speaking(9.0)
check("девять секунд её речи окно не тратят",
      talker.talking(now + 16),
      "| иначе человек говорит уже в закрытое окно")
check("а после её молчания — те же пятнадцать",
      talker.talking(now + 23) and not talker.talking(now + 25),
      f"| {round(talker._talking_until - now, 1)} с от начала")

# The ceiling still wins: a long conversation ends when it ends, and
# replies do not buy their way past it.
long_one = RinaEngine(settings=MemorySettings({
    "custom_commands": [], "reminders": [], "history": [], "todo": [],
}))
long_one._open_talk()
long_one._talking_since = _clock.monotonic() - long_one.TALK_LIMIT + 5
long_one.talk_after_speaking(60.0)
check("потолок разговора не обойти длинной репликой",
      not long_one.talking(_clock.monotonic() + 10),
      f"| осталось {round(long_one._talking_until - _clock.monotonic(), 1)} с")

# And nothing is held open when no conversation is on: an answer to a
# typed line must not make the name optional.
typed = RinaEngine(settings=MemorySettings({
    "custom_commands": [], "reminders": [], "history": [], "todo": [],
}))
typed.talk_after_speaking(9.0)
check("без разговора ответ его не открывает", not typed.talking())

print()
print("=== неизменяемость намерения ===")
i = route("запусти телеграм", ctx)
try:
    i.args["app"] = "подмена"
    check("args защищены", False)
except Exception as e:
    check("args защищены", True, f"| {type(e).__name__}")

print()
print("ИТОГО ошибок:", fails)
sys.exit(1 if fails else 0)
