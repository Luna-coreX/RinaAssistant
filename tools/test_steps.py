# -*- coding: utf-8 -*-
"""
4.0b-A09: what a sequence is built out of — waiting, repeating, choosing.

Three kinds added to steps, and every one of them is **control flow over
calls of declared tools**, not a way to run something arbitrary. A step
inside a repeat or a branch is an ordinary step and goes the same path with
the same gates; that is the line the plan draws, and letting a person say
"three times" or "only in the evening" does not cross it.

**The limits are the interesting part.** A card describes work, and a card
that can describe an unbounded amount of work is a card that can hang the
program by being written carelessly. So: a capped repeat, a capped nesting
depth, and a condition that is answered here and now rather than by going and
looking at something slow.
"""
import io
import os
import sys
import time

sys.path.insert(0, r"C:\DevStation\PCDev\DesktopApps\RinaAssistant")
sys.path.insert(0, os.path.join(
    r"C:\DevStation\PCDev\DesktopApps\RinaAssistant", "tools"))

from console import use_utf8
from core import data_transfer
from voice import user_commands
from voice.user_commands import MAX_DEPTH, MAX_REPEAT, execute

use_utf8()

fails = 0


def check(label, cond, detail=""):
    global fails
    if not cond:
        fails += 1
    print(("OK   " if cond else "FAIL "), label, detail)


#: Steps are counted through the address opener: it is the one seam a step
#: reaches for that can be replaced without touching the machine. A "say out
#: loud" step would have been the obvious choice and proves nothing —
#: `execute` returns such a step's text as its answer and never says it.
opened = []


class Opener:
    @staticmethod
    def open(url):
        opened.append(url)
        return True


def visit(name):
    return {"type": "website", "target": name, "triggers": [], "steps": []}


was = user_commands.webbrowser
user_commands.webbrowser = Opener
try:
    # --- repeating -----------------------------------------------------
    opened.clear()
    ok, _ = execute({"type": "repeat", "count": 3, "steps": [visit("a")]})
    check("повтор выполняет шаг заданное число раз",
          ok and len(opened) == 3, f"| {len(opened)}")

    opened.clear()
    execute({"type": "repeat", "count": 10 ** 6, "steps": [visit("b")]})
    check(f"и не больше предела в {MAX_REPEAT}", len(opened) == MAX_REPEAT,
          f"| {len(opened)}")

    opened.clear()
    execute({"type": "repeat", "count": -5, "steps": [visit("c")]})
    check("отрицательное число раз — ни одного", opened == [], f"| {opened}")

    # A failed round is not tried again: whatever went wrong is unlikely to
    # right itself, and repeating a failing action is the one thing nobody
    # wants a computer keen on.
    #
    # **Inside** a round a failing step does not cancel the ones after it —
    # that is how sequences have behaved since 2.0.0, and changing it here
    # would change what existing commands do. So one round runs, both its
    # steps are attempted, and there is no second round. The first version
    # of this check expected an empty list and was asserting a design
    # nobody had chosen.
    opened.clear()
    ok, _ = execute({"type": "repeat", "count": 4, "steps": [
        {"type": "выдумка", "target": "x"},
        visit("d"),
    ]})
    check("сбойный круг не повторяется",
          not ok and len(opened) == 1, f"| ok={ok}, {opened}")

    # --- choosing ------------------------------------------------------
    opened.clear()
    execute({"type": "if", "condition": "after", "value": "00:00",
             "steps": [visit("then")], "otherwise": [visit("else")]})
    check("условие «позже полуночи» ведёт в первую ветвь",
          [u.split("//")[-1] for u in opened] == ["then"], f"| {opened}")

    opened.clear()
    execute({"type": "if", "condition": "before", "value": "00:00",
             "steps": [visit("then")], "otherwise": [visit("else")]})
    check("а «раньше полуночи» — во вторую",
          [u.split("//")[-1] for u in opened] == ["else"], f"| {opened}")

    # The one that matters for safety: a condition nobody can evaluate must
    # not take the *then* branch. Taking the "otherwise" one is what a
    # person wrote for the case when it does not hold, and is the least
    # surprising reading.
    opened.clear()
    execute({"type": "if", "condition": "чего-нибудь", "value": "",
             "steps": [visit("then")], "otherwise": [visit("else")]})
    check("непонятное условие не ведёт в ветвь «тогда»",
          [u.split("//")[-1] for u in opened] == ["else"], f"| {opened}")

    opened.clear()
    execute({"type": "if", "condition": "exists", "value": __file__,
             "steps": [visit("here")], "otherwise": [visit("gone")]})
    check("условие про существующий файл выполняется",
          [u.split("//")[-1] for u in opened] == ["here"], f"| {opened}")

    # --- waiting -------------------------------------------------------
    started = time.time()
    execute({"type": "pause", "target": "0.2"})
    check("пауза действительно ждёт", time.time() - started >= 0.15,
          f"| {time.time() - started:.2f} с")

    started = time.time()
    execute({"type": "pause", "target": "9999"})
    check("и не ждёт дольше своего предела", time.time() - started < 61,
          f"| {time.time() - started:.1f} с")

    # --- nesting -------------------------------------------------------
    #
    # A card describing an unbounded amount of work must not get to do it.
    # Built rather than written out: seven levels is not something one types.
    opened.clear()
    deep = visit("bottom")
    for _ in range(MAX_DEPTH + 3):
        deep = {"type": "sequence", "target": "", "steps": [deep]}
    execute(deep)
    check("слишком глубокая вложенность не исполняется до дна",
          opened == [], f"| {opened}")

    # And an ordinary depth still works: a limit that refused two levels
    # would be a limit against the person rather than against the slip.
    opened.clear()
    execute({"type": "sequence", "steps": [
        {"type": "repeat", "count": 2, "steps": [
            {"type": "if", "condition": "after", "value": "00:00",
             "steps": [visit("ok")], "otherwise": []},
        ]},
    ]})
    check("а обычная вложенность — исполняется", len(opened) == 2,
          f"| {len(opened)}")
finally:
    user_commands.webbrowser = was


# --- these kinds are steps, not commands -----------------------------------
#
# A command of type "wait" would do nothing on purpose; one that is only a
# repeat says nothing about what it repeats. The core states this, because
# it is about what they mean.
check("ожидание, повтор и условие объявлены шагами, а не командами",
      user_commands.STEP_ONLY == {"pause", "repeat", "if"},
      f"| {sorted(user_commands.STEP_ONLY)}")
check("и все они исполнимы",
      all(k in {t for t, *_ in user_commands.COMMAND_TYPES}
          for k in user_commands.STEP_ONLY))


# --- a card from outside is narrowed in these fields too --------------------
narrowed = data_transfer.sanitize_command({
    "type": "repeat", "count": 10 ** 9, "triggers": [],
    "condition": "выдуманное",
    "steps": [{"type": "website", "target": "x"}] * 300,
    "otherwise": [{"type": "website", "target": "y"}] * 300,
})
check("ввезённый повтор ограничен", narrowed["count"] == MAX_REPEAT,
      f"| {narrowed['count']}")
check("ввезённое условие без имени не проезжает",
      narrowed["condition"] == "", f"| {narrowed['condition']!r}")
check("обе ветви ограничены по длине",
      len(narrowed["steps"]) == 50 and len(narrowed["otherwise"]) == 50,
      f"| {len(narrowed['steps'])}, {len(narrowed['otherwise'])}")

print()
print("ИТОГО ошибок:", fails)
sys.exit(1 if fails else 0)
