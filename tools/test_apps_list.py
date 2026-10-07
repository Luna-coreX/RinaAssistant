# -*- coding: utf-8 -*-
"""
The list of programs: an empty answer is not kept, and an old one is renewed.

Found by the audit of 2026-10-07 (M-4). The engine asked the shell for the
programs once per life and kept whatever came — an empty list too, when the
shell's first index did not fit into the minute it is given on a cold
start. From then on «открой телеграм» answered "not found" until Rina was
restarted. And a program installed after she started was never found at
all: neither side asked the index to be rebuilt.

Checked here with the shell substituted:

- an empty answer is not kept, and is asked again — but not on every phrase;
- a list that came is kept, and the shell is not asked on every phrase;
- an old list is renewed with `refresh`, in the background, and the phrase
  in hand does not wait for it;
- a renewal that comes back empty does not throw away a list that worked.

To run:
    python tools/test_apps_list.py
"""
import os
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

from console import use_utf8
from sandbox import neutralise

use_utf8()
neutralise()

from core.engine import RinaEngine
from core.events import EventBus
from core.settings_api import MemorySettings

fails = 0


def check(label, cond, detail=""):
    global fails
    if not cond:
        fails += 1
    print(("OK   " if cond else "FAIL "), label, detail)


NOTEPAD = {"name": "Notepad", "launch": "notepad.exe", "kind": "file",
           "source": "start_menu"}
TELEGRAM = {"name": "Telegram", "launch": "telegram.exe", "kind": "file",
            "source": "start_menu"}


class Shell:
    """`apps.index` as the shell answers it."""

    def __init__(self, answers):
        self.answers = list(answers)
        self.asked = []
        self.slow = 0.0

    def __call__(self, refresh=False):
        self.asked.append(refresh)
        if self.slow:
            time.sleep(self.slow)
        return self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]


def engine_with(shell):
    engine = RinaEngine(settings=MemorySettings({"custom_commands": []}),
                        event_bus=EventBus())
    engine.apps_source = shell
    return engine


def names(entries):
    return [e.name for e in entries]


# ---------------------------------------------------------------------------
print("=== пустой ответ не запоминается ===")
shell = Shell([[], [NOTEPAD]])
engine = engine_with(shell)
check("первый ответ пустой", engine.installed_apps() == [])
check("сразу не переспрашивает — фраза не ждёт оболочку каждый раз",
      engine.installed_apps() == [] and len(shell.asked) == 1,
      f"| спрошено {len(shell.asked)}")
engine._apps_empty_at -= engine.APPS_RETRY + 1
check("а через время спрашивает снова и находит",
      names(engine.installed_apps()) == ["Notepad"] and len(shell.asked) == 2,
      f"| спрошено {len(shell.asked)}")

# ---------------------------------------------------------------------------
print()
print("=== полученный список держится ===")
for _ in range(5):
    engine.installed_apps()
check("пять фраз — ни одного нового вопроса", len(shell.asked) == 2)

# ---------------------------------------------------------------------------
print()
print("=== старый список обновляется в фоне ===")
shell.answers = [[NOTEPAD, TELEGRAM]]
shell.slow = 0.5
engine._apps_at -= engine.APPS_FRESH + 1
began = time.monotonic()
seen = engine.installed_apps()
took = time.monotonic() - began
check("фраза отвечает по прежнему списку и не ждёт",
      names(seen) == ["Notepad"] and took < 0.3, f"| {took:.2f} с")
for _ in range(50):
    if not engine._apps_refreshing:
        break
    time.sleep(0.05)
check("оболочку попросили перестроить индекс", shell.asked[-1] is True,
      f"| {shell.asked}")
check("новая программа найдена без перезапуска",
      names(engine.installed_apps()) == ["Notepad", "Telegram"])
check("и только один фоновый вопрос, а не по одному на фразу",
      shell.asked.count(True) == 1, f"| {shell.asked}")

# ---------------------------------------------------------------------------
print()
print("=== пустое обновление не стирает рабочий список ===")
shell.answers = [[]]
shell.slow = 0.0
engine._apps_at -= engine.APPS_FRESH + 1
engine.installed_apps()
for _ in range(50):
    if not engine._apps_refreshing:
        break
    time.sleep(0.05)
check("список остался прежним",
      names(engine.installed_apps()) == ["Notepad", "Telegram"])

# ---------------------------------------------------------------------------
print()
print("=== оболочка упала — ядро нет ===")


def broken(refresh=False):
    raise RuntimeError("оболочка не ответила")


fallen = engine_with(broken)
check("ошибка источника — пустой список, а не исключение",
      fallen.installed_apps() == [])

print()
print("ИТОГО ошибок:", fails)
sys.exit(1 if fails else 0)
