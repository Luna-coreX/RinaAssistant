# -*- coding: utf-8 -*-
"""
B05: два ядра в одном процессе не мешают друг другу.

Критерий приёмки задачи. Скрытое глобальное состояние проявляется именно
здесь: если где-то остался модульный синглтон, второе ядро либо перехватит
чужое событие, либо ответит на чужой вопрос, либо оба промолчат.
"""
import os
import sys

sys.path.insert(0, r"C:\DevStation\PCDev\DesktopApps\RinaAssistant")
os.chdir(r"C:\DevStation\PCDev\DesktopApps\RinaAssistant")

from core import logging_setup
logging_setup.setup()

from core.settings_store import settings
settings.load()
settings.update({"llm_enabled": False, "web_search_fallback": True,
                 "custom_commands": [], "reminders": [], "history": []})

# Все побочные эффекты разом. Перечислять их в каждом тесте вручную —
# как было в первой редакции — значит однажды забыть один: тогда забылся
# браузер, и «да» без заданного вопроса ушло в веб-поиск настоящей
# вкладкой на машине разработчика.
from tools.sandbox import neutralise

box = neutralise()

from core.engine import RinaEngine
from core.events import EventBus, bus as global_bus

fails = 0


def check(label, cond, detail=""):
    global fails
    if not cond:
        fails += 1
    print(("OK   " if cond else "FAIL "), label, detail)


def make():
    engine = RinaEngine(event_bus=EventBus())
    engine._speak_blocking = lambda text: None
    said = []
    engine.say = lambda text, sound="response": said.append(text)
    events = []
    engine.bus.on("window.action", lambda d: events.append(d.get("action")))

    # Оболочка-заглушка: с 4.0-G01 ядро просит её сделать системное
    # действие, а не делает само (ADR 0009). Своя у каждого ядра — в этом
    # весь смысл проверки: просьба не должна уйти чужой.
    done = []
    engine.system_out = lambda action: (done.append(action), (True, ""))[1]
    engine.did = done
    return engine, said, events


A, said_a, events_a = make()
B, said_b, events_b = make()

on_global = []
global_bus.on("window.action", lambda d: on_global.append(d.get("action")))

print("=== события не растекаются ===")
# Действие окна приходит своей командой: «свернись» — это `window.action`,
# и оно осталось событием. Снимок экрана для этого больше не годится — с
# 4.0-G03 его делает оболочка системным вызовом, и события у него нет.
settings.set("custom_commands", [{
    "id": "cmd_win", "enabled": True, "type": "system", "target": "minimize",
    "triggers": ["свернись"], "match": "contains", "response": "", "steps": [],
}])
A.handle_command("свернись")
check("событие дошло до своего ядра", events_a == ["minimize"],
      f"| {events_a}")
check("чужое ядро его не увидело", events_b == [], f"| {events_b}")
check("в глобальную шину ничего не ушло", on_global == [],
      f"| {on_global}")

print()
print("=== заданный вопрос принадлежит своему ядру ===")
A.handle_command("выключи компьютер")
check("вопрос у того, кто спросил", A._dialog.current() is not None)
check("у второго вопроса нет", B._dialog.current() is None)

B.handle_command("да")
check("чужое «да» не выполнило действие",
      "Выключаю" not in (said_b[-1] if said_b else ""), f"| {said_b[-1]}")
check("браузер перехвачен, а не открыт", bool(box.opened),
      f"| {box.opened}")
check("вопрос у первого уцелел", A._dialog.current() is not None)

A.handle_command("да")
check("своё «да» выполнило действие",
      "Выключаю" in said_a[-1], f"| {said_a[-1]}")

print()
print("=== ответы не путаются ===")
before_b = len(said_b)
A.handle_command("посчитай 15*12")
check("ответ ушёл своему", "180" in said_a[-1], f"| {said_a[-1]}")
check("второму ничего не пришло", len(said_b) == before_b)

print()
print("ИТОГО ошибок:", fails)
os._exit(1 if fails else 0)
