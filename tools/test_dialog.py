# -*- coding: utf-8 -*-
"""
B03: машина состояний диалога. Проверяется без приложения.

Критерий приёмки задачи: состояние можно сохранить и восстановить.
"""
import json
import sys
import time

sys.path.insert(0, r"C:\DevStation\PCDev\DesktopApps\RinaAssistant")

from core.dialog import (CHOOSE_APP, CONFIRM_ACTION, CONFIRM_COMMAND,
                         TTL_SECONDS, Dialog, Question)
from voice.app_index import AppEntry

fails = 0


def check(label, cond, detail=""):
    global fails
    if not cond:
        fails += 1
    print(("OK   " if cond else "FAIL "), label, detail)


print("=== чистота ===")
check("Qt не загружен", "PySide6" not in sys.modules)
check("настройки не загружены", "core.settings_store" not in sys.modules)

print()
print("=== переходы ===")
d = Dialog()
check("сначала пусто", d.current() is None and not d.pending)

d.ask(Question.confirm_action("shutdown"))
check("вопрос задан", d.pending)
check("вид верный", d.current().kind == CONFIRM_ACTION)
check("действие верное", d.current().action == "shutdown")

d.answered()
check("после ответа пусто", d.current() is None)

d.ask(Question.confirm_action("restart"))
d.dropped()
check("после снятия пусто", d.current() is None)

print()
print("=== срок жизни ===")
old = Question(kind=CONFIRM_ACTION, action="shutdown",
               asked_at=time.time() - TTL_SECONDS - 1)
d = Dialog(old)
check("протухший вопрос не действует", d.current() is None)
check("протухший снимается насовсем", d._question is None)

fresh = Question(kind=CONFIRM_ACTION, action="shutdown",
                 asked_at=time.time() - 1)
check("свежий действует", Dialog(fresh).current() is not None)

print()
print("=== сериализация — критерий приёмки ===")
apps = [AppEntry("Visual Studio Code", r"C:\VSCode\Code.exe", "file", "start_menu"),
        AppEntry("Visual Studio 2022", r"C:\VS\devenv.exe", "file", "start_menu")]
d = Dialog()
d.ask(Question.choose_app(apps, query="visual studio"))

raw = json.dumps(d.to_dict(), ensure_ascii=False)
check("состояние пишется в JSON", isinstance(raw, str) and len(raw) > 10)

restored = Dialog.from_dict(json.loads(raw))
q = restored.current()
check("вопрос восстановлен", q is not None and q.kind == CHOOSE_APP)
check("запрос сохранился", q.query == "visual studio")
check("варианты сохранились", len(q.options) == 2)
check("варианты — словари, а не объекты",
      all(isinstance(o, dict) for o in q.options))

entries = q.entries()
check("варианты разворачиваются обратно в объекты",
      [e.name for e in entries] == [a.name for a in apps],
      f"| {[e.name for e in entries]}")
check("путь запуска не потерян", entries[0].launch == apps[0].launch)

for question in (Question.confirm_action("sleep"),
                 Question.confirm_command("cmd-42")):
    again = Question.from_dict(json.loads(json.dumps(question.to_dict())))
    check(f"{question.kind} переживает круг", again == question)

print()
print("=== неизменяемость ===")
q = Question.confirm_action("shutdown")
try:
    q.action = "подмена"
    check("поле защищено", False)
except Exception as e:
    check("поле защищено", True, f"| {type(e).__name__}")

try:
    Question(kind="выдумка")
    check("неизвестный вид отклонён", False)
except ValueError as e:
    check("неизвестный вид отклонён", True, f"| {e}")

print()
print("ИТОГО ошибок:", fails)
sys.exit(1 if fails else 0)
