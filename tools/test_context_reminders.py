# -*- coding: utf-8 -*-
"""
4.0b-A03: a reminder bound to a program — through the whole core.

The check goes through `RinaEngine`: the task has three joints, and each of
them can part company silently. Parsing the phrase separates the program
from the thing to do; the store has to survive an entry with no clock; an
event from the shell has to find the waiting entry and **not** find
somebody else's.

There is no shell here: `note_foreground` is called directly. That is
exactly the call the protocol makes, and there is nothing to substitute for
it — while Windows switching windows is not needed by the check.
"""
import sys
import time

sys.path.insert(0, r"C:\DevStation\PCDev\DesktopApps\RinaAssistant")

from core.engine import RinaEngine
from core.protocol import Events
from core.settings_api import MemorySettings
from voice.app_index import AppEntry

fails = 0


def check(label, cond, detail=""):
    global fails
    if not cond:
        fails += 1
    print(("OK   " if cond else "FAIL "), label, detail)


CODE = r"C:\VSCode\Code.exe"
OBS = r"C:\obs\obs64.exe"
APPS = [
    AppEntry("Visual Studio Code", CODE, "file", "start_menu"),
    AppEntry("Visual Studio 2022", r"C:\VS\devenv.exe", "file", "start_menu"),
    AppEntry("OBS Studio", OBS, "file", "start_menu"),
]


class Session:
    def __init__(self, watch=True):
        self.settings = MemorySettings({
            "watch_apps": watch, "app_aliases": {}, "custom_commands": [],
            "reminders": [], "history": [],
        })
        self.engine = RinaEngine(settings=self.settings)
        # Nothing is opened on anybody's machine: see `test_learning.py`.
        self.opened = []
        self.engine.browser_out = lambda url: (self.opened.append(url),
                                               (True, ""))[1]
        self.engine.apps_source = lambda: [a.to_dict() for a in APPS]
        self.said = []
        self.engine.voice_out = lambda text, **kw: self.said.append(text)
        self.fired = []
        self.engine.bus.on(Events.REMINDER_FIRED,
                           lambda data: self.fired.append(data["item"]))

    def say(self, phrase):
        self.said = []
        self.engine.handle_command(phrase, source="typed")
        return " ".join(self.said)

    @property
    def planned(self):
        return self.engine._reminders.active()


print("=== завести ===")
s = Session()
answer = s.say("напомни проверить pr когда открою visual studio code")
check("принято", "Visual Studio Code" in answer, f"| {answer}")
check("запланировано ровно одно", len(s.planned) == 1, f"| {s.planned}")

item = s.planned[0] if s.planned else {}
check("дело отделено от программы", item.get("text") == "проверить pr",
      f"| {item.get('text')!r}")
check("привязано к пути, а не к имени",
      (item.get("on") or {}).get("launch") == CODE, f"| {item.get('on')}")
# Such a reminder has no clock at all. Zero is the year 1970, and the
# scheduler would consider the entry half a century overdue: it would fire
# a second after it was created.
check("часов нет, и они не в прошлом", not item.get("fire_at"),
      f"| {item.get('fire_at')}")
check("планировщик его не берёт", not s.engine._reminders.due(time.time()),
      f"| {s.engine._reminders.due(time.time())}")

print()
print("=== сработать ===")
check("чужая программа не будит", s.engine.note_foreground(OBS) == 0)
check("и напоминание на месте", len(s.planned) == 1, f"| {s.planned}")

check("своя программа будит", s.engine.note_foreground(CODE) == 1)
check("событие ушло наружу", len(s.fired) == 1, f"| {s.fired}")
check("и в событии сказано, что сработало",
      bool(s.fired) and s.fired[0].get("done") is True, f"| {s.fired}")
check("второй раз не будит", s.engine.note_foreground(CODE) == 0)
check("больше ничего не ждёт", not s.planned, f"| {s.planned}")

print()
print("=== регистр пути ===")
s = Session()
s.say("напомни слить ветку когда открою visual studio code")
check("windows не различает регистр — и мы не различаем",
      s.engine.note_foreground(CODE.upper()) == 1)

print()
print("=== переживает перезапуск ===")
s = Session()
s.say("напомни проверить pr когда открою visual studio code")
again = RinaEngine(settings=s.settings)
again.apps_source = s.engine.apps_source
again.voice_out = lambda text, **kw: None
# The store used to throw away everything without an intelligible clock —
# a rule that was right exactly as long as no other occasions existed. An
# entry bound to an event has no clock by construction.
check("новое ядро видит запланированное", len(again._reminders.active()) == 1,
      f"| {again._reminders.active()}")
check("и оно срабатывает", again.note_foreground(CODE) == 1)

print()
print("=== чего не бывает ===")
s = Session()
answer = s.say("напомни когда открою visual studio проверить почту")
check("спорное спрашивает, а не решает",
      "Visual Studio Code" in answer and "Visual Studio 2022" in answer,
      f"| {answer}")
check("спорное ничего не планирует", not s.planned, f"| {s.planned}")

answer = s.say("напомни когда открою фотошоп что-нибудь")
check("несуществующее — отказ", "не нашла" in answer.lower(), f"| {answer}")
check("и ничего не запланировано", not s.planned, f"| {s.planned}")

print()
print("=== выключенная слежка ===")
s = Session(watch=False)
answer = s.say("напомни проверить pr когда открою visual studio code")
check("отказ, а не тихое согласие", "не слежу" in answer, f"| {answer}")
check("ничего не заведено", not s.planned, f"| {s.planned}")
# Even if an entry appears by some other route, an event will not wake it:
# the watch is off, and the shell sends nothing at all.
check("обычное напоминание по часам работает и так",
      "10 мин" in s.say("напомни через 10 минут выключить чайник"),
      f"| {s.said}")

print()
print("ИТОГО ошибок:", fails)
sys.exit(1 if fails else 0)
