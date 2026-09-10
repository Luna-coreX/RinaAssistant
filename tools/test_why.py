# -*- coding: utf-8 -*-
"""
4.0b-B04: "Why?" — an explanation traceable to a journal record.

Through a real `RinaEngine`, because the point of the item is that the
explanation and the deed come from the same place. An explanation assembled
in a test out of a hand-written record would prove that the sentence
formatter works, which nobody doubted.

**Three things are worth checking, and the third is the trap.**

That a deed can be explained at all. That a **refusal** can — it is the case
a person actually comes asking about, and the journal keeps refusals on a par
with successes precisely for it. And that asking twice gives the same answer:
asking "why" is itself a call and lands in the journal, so without care the
second "why" is answered with "because you asked why" — an explanation of the
explaining.
"""
import os
import sys

sys.path.insert(0, r"C:\DevStation\PCDev\DesktopApps\RinaAssistant")
sys.path.insert(0, os.path.join(
    r"C:\DevStation\PCDev\DesktopApps\RinaAssistant", "tools"))

from console import use_utf8
from core import why
from core.audit import AuditLog
from core.engine import RinaEngine
from core.router import RouterContext, route
from core.settings_api import MemorySettings

use_utf8()

fails = 0


def check(label, cond, detail=""):
    global fails
    if not cond:
        fails += 1
    print(("OK   " if cond else "FAIL "), label, detail)


class Session:
    """A core with a journal of its own and no way out to the machine."""

    def __init__(self):
        self.settings = MemorySettings({
            "custom_commands": [], "history": [], "reminders": [], "todo": [],
        })
        self.engine = RinaEngine(settings=self.settings)
        # A journal in memory: the real one belongs to whoever is running
        # this machine, and a check has no business writing into it.
        self.engine._tools._audit = AuditLog(":memory:")
        self.engine._tools._ctx.journal = self.engine._tools._audit
        self.said = []
        self.engine.voice_out = lambda text, **kw: self.said.append(text)
        self.engine.browser_out = lambda url: (False, "")

    def say(self, phrase):
        self.said = []
        self.engine.handle_command(phrase, source="typed")
        return " ".join(self.said)


# --- the word reaches the right stage, and only from the right phrases -----
#
# "Почему трава зелёная" is a question about the world. Answered with
# "because you pressed a button" it would be worse than not understood at
# all, so the boundary is checked in both directions.
ctx = RouterContext()
mine = ["почему?", "почему ты открыла хром", "зачем ты это сделала",
        "объясни", "а почему"]
theirs = ["почему трава зелёная", "зачем мне это", "почему тыква оранжевая"]
check("вопрос о себе доходит до объяснения",
      all(route(p, ctx).name == "why.last" for p in mine),
      f"| {[route(p, ctx).name for p in mine]}")
check("вопрос о мире не перехватывается",
      all(route(p, ctx).name != "why.last" for p in theirs),
      f"| {[route(p, ctx).name for p in theirs]}")

# --- a deed, and then the question ----------------------------------------
s = Session()
s.say("запиши купить хлеб")
answer = s.say("почему?")
check("объяснение называет сделанное",
      "дело" in answer.lower(), f"| «{answer}»")
check("и говорит, кто попросил",
      "напечатал" in answer.lower(), f"| «{answer}»")

# --- and it is traceable to a record ---------------------------------------
#
# Not "the sentence mentions a thing to do" but "the sentence came from the
# journal": the explanation is asked to name the record it was built from,
# and that record is looked up.
last = why.last_doing(s.engine._tools.audit)
check("объяснение возводится к записи журнала",
      last is not None and last.get("tool") == "add_todo",
      f"| {last and last.get('tool')}")

# --- asking twice does not explain the asking ------------------------------
again = s.say("почему?")
check("второе «почему» отвечает о деле, а не о вопросе",
      again == answer, f"| «{again}»")

# --- a refusal explains itself --------------------------------------------
#
# The case a person actually comes asking about. Made by asking for
# something irreversible without a confirmation: the gate refuses, the
# journal records the refusal, and the explanation has to name the gate.
s = Session()
s.engine._tools.call("power_action", {"action": "shutdown"}, source="typed")
refusal = s.say("почему?")
check("отказ объясняется",
      "не выполнено" in refusal, f"| «{refusal}»")
check("и называет именно подтверждение",
      "подтверждени" in refusal.lower(), f"| «{refusal}»")

# --- where the path came from ----------------------------------------------
#
# "Откуда взялся этот путь" is named in the plan, and it cannot be worked out
# after the fact: by then there is a path and no memory of whether it came
# from a word the person taught or from the Start menu. It is written down at
# the moment of the decision — so this goes **through a real launch**, not
# through a record typed out here.
#
# The first version of this check did type the record out, and paid for it:
# taking the recording out of `_launch_app` left it green. It was measuring
# the sentence formatter, which nobody doubted.
def launching(source):
    """A core whose index holds one program from a named source."""
    made = Session()
    made.engine.apps_source = lambda: [
        {"name": "блокнот", "launch": r"C:\Windows\notepad.exe",
         "kind": "file", "source": source},
    ]
    made.engine.launch_out = lambda launch, kind: (True, "")
    made.engine._tools.call("launch_app", {"name": "блокнот"}, source="voice")
    return made


taught = launching("learned")
made = taught.say("почему?")
check("объяснение называет источник пути",
      "задали сами" in made, f"| «{made}»")

menu = launching("start_menu")
other = menu.say("почему?")
check("и различает источники", "Пуск" in other and made != other,
      f"| «{other}»")

# --- nothing done, nothing invented ----------------------------------------
s = Session()
nothing = s.say("почему?")
check("без единого действия объяснять нечего",
      "ничего не делала" in nothing, f"| «{nothing}»")

print()
print("ИТОГО ошибок:", fails)
sys.exit(1 if fails else 0)
