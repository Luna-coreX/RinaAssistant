# -*- coding: utf-8 -*-
"""
B05: two cores in one process do not get in each other's way.

The task's acceptance criterion. Hidden global state shows up precisely
here: if a module singleton is left somewhere, the second core will either
intercept the other's event, or answer the other's question, or both will
stay silent.
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

# Every side effect at once. Listing them by hand in every test — as the
# first edition did — means forgetting one some day: back then the browser
# was forgotten, and a "yes" without a question asked went into a web search
# as a real tab on the developer's machine.
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

    # A stub shell: since 4.0-G01 the core asks it to perform a system
    # action rather than performing it itself (ADR 0009). One per core — that
    # is the whole point of the check: a request must not go to the wrong
    # one.
    done = []
    engine.system_out = lambda action: (done.append(action), (True, ""))[1]
    engine.did = done
    return engine, said, events


A, said_a, events_a = make()
B, said_b, events_b = make()

on_global = []
global_bus.on("window.action", lambda d: on_global.append(d.get("action")))

print("=== события не растекаются ===")
# A window action comes as a command of its own: "свернись" is
# `window.action`, and it stayed an event. A screenshot no longer suits that
# — since 4.0-G03 the shell takes it with a system call, and it has no
# event.
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
