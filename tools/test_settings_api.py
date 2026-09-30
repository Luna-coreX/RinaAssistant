# -*- coding: utf-8 -*-
"""
B06: ядро получает настройки через интерфейс, а не через синглтон.

Смысл проверки: два ядра с разными настройками ведут себя по-разному, и файл
пользователя при этом не трогается вовсе.
"""
import os
import sys

sys.path.insert(0, r"C:\DevStation\PCDev\DesktopApps\RinaAssistant")
sys.path.insert(0, r"C:\DevStation\PCDev\DesktopApps\RinaAssistant\tools")
os.chdir(r"C:\DevStation\PCDev\DesktopApps\RinaAssistant")

from core import logging_setup
logging_setup.setup()

from sandbox import neutralise
box = neutralise()

from core.engine import RinaEngine
from core.events import EventBus
from core.settings_api import MemorySettings, SettingsProvider, default_settings

fails = 0


def check(label, cond, detail=""):
    global fails
    if not cond:
        fails += 1
    print(("OK   " if cond else "FAIL "), label, detail)


print("=== интерфейс ===")
mem = MemorySettings()
check("MemorySettings удовлетворяет протоколу",
      isinstance(mem, SettingsProvider))
check("общее хранилище тоже удовлетворяет",
      isinstance(default_settings(), SettingsProvider))

check("значение по умолчанию читается",
      mem.get("wake_word") == "Рина", f"| {mem.get('wake_word')}")
mem.set("wake_word", "Мира")
check("значение записывается", mem.get("wake_word") == "Мира")
before = mem.saves
mem.save()
check("сохранение считается", mem.saves == before + 1)

with mem.transaction():
    mem.set("volume", 42)
check("транзакция работает", mem.get("volume") == 42)


def make(values):
    settings = MemorySettings(values)
    engine = RinaEngine(event_bus=EventBus(), settings=settings)
    engine._speak_blocking = lambda text: None
    said = []
    engine.say = lambda text, sound="response": said.append(text)
    return engine, settings, said


print()
print("=== разные настройки — разное поведение ===")
A, a_set, said_a = make({"web_search_fallback": True, "llm_enabled": False})
B, b_set, said_b = make({"web_search_fallback": False, "llm_enabled": False})

A.handle_command("столица австралии")
B.handle_command("столица австралии")
check("с запасным поиском — ищет",
      "поищу" in said_a[-1], f"| {said_a[-1]}")
check("без запасного поиска — отказ",
      "не поняла" in said_b[-1], f"| {said_b[-1]}")

print()
print("=== состояние не пересекается ===")
check("история пишется каждому своя",
      len(a_set.get("history")) == 1 and len(b_set.get("history")) == 1,
      f"| A={len(a_set.get('history'))}, B={len(b_set.get('history'))}")

A.handle_command("поставь таймер на 10 минут")
check("напоминание только у A",
      len(a_set.get("reminders")) == 1 and len(b_set.get("reminders")) == 0,
      f"| A={len(a_set.get('reminders'))}, B={len(b_set.get('reminders'))}")

print()
print("=== файл пользователя не тронут ===")
real = default_settings()
check("общее хранилище не использовалось ядрами",
      A._settings is not real and B._settings is not real)
check("слово активации в общем хранилище не менялось",
      real.get("wake_word") == "Рина", f"| {real.get('wake_word')}")

print()
print("=== по умолчанию — общее хранилище ===")
plain = RinaEngine(event_bus=EventBus())
check("без аргумента берётся общее хранилище",
      plain._settings is real)

print()
print("ИТОГО ошибок:", fails)
os._exit(1 if fails else 0)
