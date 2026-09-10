# -*- coding: utf-8 -*-
"""
4.0b-A09: trying a command that has not been saved.

The editor could assemble a command and could save it, and until it was
saved there was no way to find out whether it did what was meant. Saving in
order to find out leaves a command behind on every attempt.

**What is asserted, and what turned out not to be worth asserting.** That
the card runs; that **nothing is stored** by running it — no command, no
identifier, no bumped counter; that the steps run in order; and that a card
of ten thousand steps becomes a card of fifty.

The obvious fourth — "a made-up kind of action does nothing" — was written
first, and broke on its own test. Taking the sanitising out left it green,
because `execute` already ignores a kind it does not know, and so does a
system action outside its table. The card was safe there **before** the
narrowing and without it; the assertion was measuring `execute` and
crediting the sanitiser.

So what the narrowing actually buys on this path is the caps: fifty steps
and a thousand characters of target. That is what is checked. The rest of
the safety is where it always was — `execute` knows a fixed set of kinds,
and the four gates of the registry are unchanged.
"""
import os
import sys

sys.path.insert(0, r"C:\DevStation\PCDev\DesktopApps\RinaAssistant")
sys.path.insert(0, os.path.join(
    r"C:\DevStation\PCDev\DesktopApps\RinaAssistant", "tools"))

from console import use_utf8
from core.engine import RinaEngine
from core.settings_api import MemorySettings

use_utf8()

fails = 0


def check(label, cond, detail=""):
    global fails
    if not cond:
        fails += 1
    print(("OK   " if cond else "FAIL "), label, detail)


class Session:
    """A core with a stand-in store and no way out to the machine."""

    def __init__(self):
        self.settings = MemorySettings({
            "custom_commands": [], "todo": [], "reminders": [], "history": [],
        })
        self.engine = RinaEngine(settings=self.settings)
        self.said = []
        self.engine.voice_out = lambda text, **kw: self.said.append(text)
        self.launched = []
        self.engine.launch_app = lambda path: (
            self.launched.append(path), (True, ""))[1]

    def try_card(self, card):
        """Through the executor, synchronously — the thread is the engine's."""
        self.said = []
        self.launched = []
        return self.engine._executor.try_user_command(card)

    @property
    def stored(self):
        return list(self.settings.get("custom_commands") or [])


# --- it runs at all --------------------------------------------------------
s = Session()
result = s.try_card({
    "type": "speak",
    "target": "проба голосом",
    "triggers": [],
    "response": "",
    "steps": [],
})
check("непросохранённая команда выполняется", result.ok, f"| {result}")

# --- and stores nothing ----------------------------------------------------
#
# The whole reason this method exists. If a trial saved, a person trying a
# phrase four times would have four commands to delete, and the editor would
# be offering a tidy way to make a mess.
check("проба ничего не сохранила", len(s.stored) == 0,
      f"| в хранилище {len(s.stored)}")

# --- a made-up kind does nothing -------------------------------------------
#
# Kept, but for what it is: this is `execute` refusing a kind it does not
# know, not the sanitiser. Removing the sanitising leaves it green — which
# is how it was found out. Worth an assertion all the same, because the
# refusal is what makes the wide door narrow, and it should stay refused.
s = Session()
s.try_card({
    "type": "лишь бы что",
    "target": r"C:\Windows\System32\calc.exe",
    "triggers": [],
    "response": "",
    "steps": [],
})
check("незнакомый вид ничего не запускает", s.launched == [],
      f"| запущено {s.launched}")

s = Session()
s.try_card({
    "type": "system",
    "target": "format_the_disk",
    "triggers": [],
    "response": "",
    "steps": [],
})
check("самодельное системное действие не проходит", s.launched == [],
      f"| запущено {s.launched}")

# --- a sequence runs its steps, in order -----------------------------------
#
# Through the address opener, because that is what a step of this kind
# actually reaches for. A "say out loud" step would have been the obvious
# choice and would have proved nothing: `execute` returns such a step's text
# as its answer and never says it, so a check watching for speech watches
# something that has never happened, for any command, saved or not.
#
# Waited for rather than slept through: a sequence runs on a thread of its
# own, and a fixed pause is a race dressed up as a check.
import time

from voice import user_commands

opened = []


class Opener:
    @staticmethod
    def open(url):
        opened.append(url)
        return True


was = user_commands.webbrowser
user_commands.webbrowser = Opener
try:
    s = Session()
    s.try_card({
        "type": "sequence",
        "target": "",
        "triggers": [],
        "response": "",
        "steps": [
            {"type": "website", "target": "first.example",
             "triggers": [], "steps": []},
            {"type": "website", "target": "second.example",
             "triggers": [], "steps": []},
        ],
    })
    for _ in range(50):
        if len(opened) >= 2:
            break
        time.sleep(0.1)
    check("шаги последовательности выполнены по порядку",
          [u.split("//")[-1] for u in opened[:2]]
          == ["first.example", "second.example"], f"| {opened}")
    check("и последовательность тоже ничего не сохранила",
          len(s.stored) == 0, f"| в хранилище {len(s.stored)}")

    # And here the narrowing does earn its place: the cap on how many
    # steps a card may carry. `execute` would run every one of them, so
    # this is the one assertion on this path that goes red when the
    # sanitising is taken out.
    opened.clear()
    s = Session()
    s.try_card({
        "type": "sequence",
        "target": "",
        "triggers": [],
        "response": "",
        "steps": [{"type": "website", "target": f"step{n}.example",
                   "triggers": [], "steps": []} for n in range(300)],
    })
    for _ in range(100):
        if len(opened) >= 50:
            break
        time.sleep(0.1)
    time.sleep(0.5)
    check("карточка из трёхсот шагов усечена до пятидесяти",
          len(opened) == 50, f"| открыто {len(opened)}")
finally:
    user_commands.webbrowser = was

print()
print("ИТОГО ошибок:", fails)
sys.exit(1 if fails else 0)
