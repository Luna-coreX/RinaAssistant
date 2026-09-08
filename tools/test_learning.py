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

from core.engine import RinaEngine
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
        self.settings = MemorySettings({
            "app_aliases": {}, "custom_commands": [],
            "reminders": [], "history": [],
        })
        self.engine = RinaEngine(settings=self.settings)
        self.engine.apps_source = lambda: [a.to_dict() for a in APPS]
        self.launched = []
        self.engine.launch_out = self._launch
        self.said = []
        self.engine.voice_out = lambda text, **kw: self.said.append(text)

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
print("=== два ядра не делят выученное ===")
a, b = Session(), Session()
a.say("когда я говорю код, запускай Visual Studio Code")
check("соседнее ядро ничего не выучило", not b.learned, f"| {b.learned}")

print()
print("ИТОГО ошибок:", fails)
sys.exit(1 if fails else 0)
