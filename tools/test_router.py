# -*- coding: utf-8 -*-
"""B02: роутер — чистая функция. Проверяется без приложения."""
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

always = RouterContext(apps=APPS, source="always")
check("в режиме «всегда слушать» поиска нет",
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
wake_always = RouterContext(apps=APPS, require_wake=True, source="always")
check("голое слово в режиме «всегда» — молчание",
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

# Вопрос всегда приходит сериализованным: роутер работает с состоянием,
# которое можно записать в файл и отправить по протоколу (4.0-B03).
choose = RouterContext(apps=APPS, pending=Question.choose_app(
    APPS[2:4], query="visual studio").to_dict())
picked = route("второй", choose)
check("выбор порядковым", picked.name == "app.launch"
      and picked.arg("app") == "Visual Studio 2022", f"| {picked}")
check("выбор именем",
      route("visual studio code", choose).arg("app") == "Visual Studio Code")
check("отмена выбора", route("отмена", choose).name == "cancelled")

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
