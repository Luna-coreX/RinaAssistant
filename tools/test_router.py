# -*- coding: utf-8 -*-
"""B02: the router is a pure function. Checked without the application."""
import sys

sys.path.insert(0, r"C:\DevStation\PCDev\DesktopApps\RinaAssistant")

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
