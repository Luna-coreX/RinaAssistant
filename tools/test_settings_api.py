# -*- coding: utf-8 -*-
"""
B06: the core gets its settings through an interface, not through a
singleton.

The point of the check: two cores with different settings behave
differently, and the user's file is not touched at all.
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
print("=== список целиком пишется под замком ===")

# Read-modify-write without a shared lock loses somebody else's edit
# entirely rather than key by key: the second thread writes its own list
# over the first. The user's commands have two such threads — an import
# from a file and an answer from Rina; the reminders have two as well —
# the scheduler marking what fired and the person creating something
# new.
import threading

from core.settings_api import MemorySettings
from voice.user_commands import UserCommandStore


class RaceSettings(MemorySettings):
    """
    A store on which the race happens **always**, not sometimes.

    The two previous editions of this check were no good, and both for
    the same reason: they relied on the scheduler's luck. The first ran
    forty threads in a loop, and each finished before the next started.
    The second added a barrier and a delay — and behaved indecently: with
    twenty threads one record out of twenty survived, with forty nothing
    was lost at all. A check that is green every other time is worse than
    no check: people stop believing it, and then stop believing the rest.

    There is no luck here. There are two threads, and the read does not
    return until the second has read as well. With no shared lock both see
    the same list and the second overwrites the first; always. With the
    lock the second never gets as far as reading, the rendezvous does not
    happen, the wait times out and everything goes as it should; always
    too.
    """

    def __init__(self, values, meeting):
        super().__init__(values)
        self._meeting = meeting

    def get(self, key, default=None):
        value = super().get(key, default)
        if key == "custom_commands":
            try:
                # The timeout is for the case where the lock is in
                # place: there the rendezvous never happens, and waiting
                # for it for ever would hang the check instead of passing
                # it.
                self._meeting.wait(timeout=1.0)
            except threading.BrokenBarrierError:
                pass
        return value


meeting = threading.Barrier(2)
shared = RaceSettings({"custom_commands": []}, meeting)
store = UserCommandStore(shared)


def add_one(number):
    # There is deliberately no transaction here: `merge` itself is
    # obliged to hold one, and that is the whole point of the check. Had
    # we wrapped the call from outside, the check would have passed with
    # the old code too — that is, it would have agreed with its author.
    store.merge([{"id": f"cmd_{number}", "type": "speak",
                  "triggers": [f"фраза {number}"], "enabled": False}],
                lambda n=number: f"cmd_{n}")


threads = [threading.Thread(target=add_one, args=(i,)) for i in (1, 2)]
for t in threads:
    t.start()
for t in threads:
    t.join()

survived = store.all()
check("запись не потеряна, когда двое пишут разом",
      len(survived) == 2, f"| дожило {len(survived)} из 2")
check("и номера не задвоились",
      len({c["id"] for c in survived}) == len(survived),
      f"| {len({c['id'] for c in survived})} разных из {len(survived)}")

print()
print("ИТОГО ошибок:", fails)

# `os._exit` is needed because the core's background threads keep the
# process alive. But it does not flush the buffers, and until this line
# the whole output of the check went nowhere: in the regression run it
# showed as an empty line, and on a failure there was no way to find out
# what exactly had failed.
sys.stdout.flush()
sys.stderr.flush()
os._exit(1 if fails else 0)
