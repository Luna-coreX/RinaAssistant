# -*- coding: utf-8 -*-
"""
4.0b-A04: learning from corrections — through the whole core.

The check goes through `RinaEngine` rather than through the router: half
the task is **where** what is learned ends up. The router on a stand-in
context answered correctly even while the entry went off into the person's
real settings past the core that learned it — a session with a stand-in
store wrote into somebody else's file, and two cores in one process
silently shared their matches.

The paths are real (`sys.executable`, `README.md`): `alias_lookup` throws
away a learned entry whose path does not exist, as stale. On made-up paths
this check would measure not the match but the mere fact of writing — and
would agree with itself while the reading was broken.
"""
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
# Storage is moved as well. These tests bring their own settings, but
# not their own call journal or logs, and those went into the
# developer's profile — measured: every check left like this wrote
# `audit.db` there, the journal Rina answers «почему?» from.
from sandbox import neutralise

neutralise()

from core.engine import RinaEngine
from core.events import EventBus
from core.protocol import Events
from core.settings_api import MemorySettings
from voice.app_index import AppEntry

fails = 0


def check(label, cond, detail=""):
    global fails
    if not cond:
        fails += 1
    print(("OK   " if cond else "FAIL "), label, detail)


HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CODE = sys.executable
CHROME = os.path.join(HERE, "README.md")
CHROMIUM = os.path.join(HERE, "LICENSE")
for path in (CODE, CHROME, CHROMIUM):
    if not os.path.exists(path):
        print("FAIL  проверке нужен существующий файл:", path)
        sys.exit(1)

APPS = [
    AppEntry("Visual Studio Code", CODE, "file", "start_menu"),
    AppEntry("Google Chrome", CHROME, "file", "start_menu"),
    AppEntry("Chromium", CHROMIUM, "file", "start_menu"),
]


class Session:
    """A core with a stand-in store and a stand-in launcher."""

    def __init__(self):
        # The search on an unrecognised phrase is off by default since
        # 2026-09-29; the seam below is about what happens when it is on,
        # so it is switched on here rather than inherited.
        self.settings = MemorySettings({
            "app_aliases": {}, "custom_commands": [],
            "reminders": [], "history": [],
            "web_search_fallback": True,
        })
        self.engine = RinaEngine(settings=self.settings, event_bus=EventBus())
        self.engine.apps_source = lambda: [a.to_dict() for a in APPS]
        self.launched = []
        self.engine.launch_out = self._launch
        # Nothing is opened on anybody's machine. An unrecognised phrase
        # falls through to the web search, and this check feeds in phrases
        # that are meant not to be recognised — so without this it opened
        # the person's browser on every run. Recorded rather than
        # suppressed: what would have been opened is worth being able to
        # assert about.
        self.opened = []
        self.engine.browser_out = self._open
        self.said = []
        # The answer, not the voice: `say` speaks on a thread of its own,
        # and reading what reached `voice_out` right after the command is
        # a race (the one tools/test_sessions.py lost once the core stopped
        # fetching programs before every command). The answer event is
        # sent before that thread starts; the bus is this engine's own.
        self.engine.bus.on(Events.RESPONSE,
                           lambda data: self.said.append(data["text"]))
        self.engine.voice_out = lambda text, **kw: None

    def _open(self, url):
        self.opened.append(url)
        return True, ""

    def _launch(self, path, kind):
        self.launched.append(path)
        return True, ""

    def say(self, phrase):
        self.said = []
        self.engine.handle_command(phrase, source="typed")
        return " ".join(self.said)

    @property
    def learned(self):
        return self.settings.get("app_aliases") or {}


print("=== названное правило ===")
s = Session()
answer = s.say("когда я говорю код, запускай Visual Studio Code")
check("правило принято", "Visual Studio Code" in answer, f"| {answer}")
check("правило записано в своё хранилище", "код" in s.learned,
      f"| {s.learned}")

# The index does not find the word "код" (checked below), so launching is
# possible only through what was learned.
answer = s.say("запусти код")
check("выученное слово запускает", s.launched == [CODE], f"| {answer}")

s2 = Session()
check("без правила слово не находится",
      "не нашла" in s2.say("запусти код").lower())

print()
print("=== поправка вслед запуску ===")
s = Session()
first = s.say("запусти хром")
check("сначала запускается своё", s.launched == [CHROME], f"| {first}")

# A launch by itself also remembers the choice — and is obliged to put it
# in the same store. The assertion here is not about "it was remembered"
# but about "where": this path does not go through the tool registry but
# through `on_alias`, and once wrote into the shared singleton — that is,
# into the person's real file, from any check.
check("запуск запоминает в своё хранилище",
      s.learned.get("хром", {}).get("name") == "Google Chrome",
      f"| {s.learned}")

answer = s.say("нет, я имел в виду Chromium")
check("поправка принята", "Chromium" in answer, f"| {answer}")
check("поправка записана", s.learned.get("хром", {}).get("name") == "Chromium",
      f"| {s.learned}")

s.launched = []
s.say("запусти хром")
# The main assertion of the whole check: what was learned is **stronger**
# than what the index would have picked by itself. Without this a
# "correction" would be an entry nobody reads.
check("выученное сильнее индекса", s.launched == [CHROMIUM], f"| {s.launched}")

print()
print("=== чего не бывает ===")
s = Session()
answer = s.say("нет, я имел в виду Google Chrome")
check("поправка без запуска ничего не выдумывает", not s.learned,
      f"| {s.learned}")

answer = s.say("когда я говорю жаба, запускай Eclipse")
check("нечего запоминать — отказ", "не нашла" in answer.lower(), f"| {answer}")
check("несуществующее не записано", not s.learned, f"| {s.learned}")

answer = s.say("когда я говорю браузер, это хром")
check("спорное спрашивает, а не решает",
      "Google Chrome" in answer and "Chromium" in answer, f"| {answer}")
check("спорное не записано молча", not s.learned, f"| {s.learned}")

print()
print("=== проверка не лезет в чужую машину ===")
# The phrases above are meant not to be recognised, and an unrecognised
# phrase falls through to the web search. Before the seam existed this
# opened the person's browser on every run of the regression — found by the
# person, who watched «я имел в виду Google Chrome» arrive in their search
# bar. A check that acts on the machine it runs on is not a check.
s = Session()
s.say("нет, я имел в виду Google Chrome")
check("нераспознанное ушло бы в поиск", len(s.opened) == 1,
      f"| открыто: {s.opened}")
check("и это адрес поиска, а не что попало",
      bool(s.opened) and s.opened[0].startswith("https://"),
      f"| {s.opened[:1]}")

print()
print("=== два ядра не делят выученное ===")
a, b = Session(), Session()
a.say("когда я говорю код, запускай Visual Studio Code")
check("соседнее ядро ничего не выучило", not b.learned, f"| {b.learned}")

print()
print("=== ядро не ждёт список программ ради суммы ===")
# The router asks for the list only in the stages about programs; this is
# the core's half of that promise — it hands over a way to get the list
# rather than the list. Handed the list itself, every command waited for
# the shell to build it.
counted = Session()
asked = []
counted.engine.apps_source = lambda: asked.append(1) or [a.to_dict()
                                                         for a in APPS]
counted.say("посчитай 15 умножить на 12")
check("сумма посчитана, а список программ не спрошен", not asked,
      f"| спрошено {len(asked)} раз")
counted.say("запусти хром")
check("а запуск его спросил", len(asked) == 1, f"| спрошено {len(asked)} раз")

print()
print("ИТОГО ошибок:", fails)
sys.exit(1 if fails else 0)
