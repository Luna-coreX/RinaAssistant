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
from voice.user_commands import (MAX_DEPTH, MAX_REPEAT,
                                 MAX_WHILE, execute)

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
    # --- stopping -------------------------------------------------------
    #
    # "Stop the scenario" has to unwind through whatever it is inside. A
    # flag returned upwards would need every repeat and every branch to
    # remember to look at it, and the one that forgot would carry on after
    # the person said to stop — which is why this is checked from inside a
    # repeat inside a branch rather than at the top.
    opened.clear()
    execute({"type": "sequence", "steps": [
        visit("before"),
        {"type": "if", "condition": "after", "value": "00:00", "steps": [
            {"type": "repeat", "count": 5, "steps": [
                visit("inside"),
                {"type": "stop"},
            ]},
        ], "otherwise": []},
        visit("after"),
    ]})
    check("«остановить» останавливает сценарий, а не ветвь",
          [u.split("//")[-1] for u in opened] == ["before", "inside"],
          f"| {opened}")

    # --- variables ------------------------------------------------------
    opened.clear()
    execute({"type": "sequence", "steps": [
        {"type": "set", "name": "режим", "target": "вечер"},
        {"type": "if", "condition": "var_is", "name": "режим",
         "value": "вечер", "steps": [visit("evening")],
         "otherwise": [visit("morning")]},
    ]})
    check("запомненное значение видно условию",
          [u.split("//")[-1] for u in opened] == ["evening"], f"| {opened}")

    # And a variable nobody set is not a variable that equals nothing: the
    # branch that acts must not run on a value that was never written.
    opened.clear()
    execute({"type": "if", "condition": "var_set", "name": "нет-такой",
             "steps": [visit("set")], "otherwise": [visit("unset")]})
    check("незаданное значение — не задано",
          [u.split("//")[-1] for u in opened] == ["unset"], f"| {opened}")

    # --- repeating while -------------------------------------------------
    opened.clear()
    execute({"type": "sequence", "steps": [
        {"type": "set", "name": "флаг", "target": "да"},
        {"type": "while", "condition": "var_is", "name": "флаг",
         "value": "да", "steps": [
             visit("round"),
             {"type": "set", "name": "флаг", "target": "нет"},
         ]},
    ]})
    check("«повторять пока» останавливается, когда условие перестаёт держаться",
          len(opened) == 1, f"| {len(opened)}")

    # The one that matters: a condition that never stops holding is not a
    # mistake anybody notices while writing it.
    opened.clear()
    ok, _ = execute({"type": "sequence", "steps": [
        {"type": "set", "name": "вечно", "target": "да"},
        {"type": "while", "condition": "var_is", "name": "вечно",
         "value": "да", "steps": [visit("forever")]},
    ]})
    check(f"и не крутится дольше предела в {MAX_WHILE}",
          len(opened) == MAX_WHILE and not ok, f"| {len(opened)}, ok={ok}")

    # --- calling another command -----------------------------------------
    store = {
        "cmd_a": {"id": "cmd_a", "type": "sequence",
                  "steps": [visit("из-другой")]},
        # A step **before** the recursion, so how far the ring got is
        # visible. Without it the depth limit stops the ring too, and an
        # assertion about "was it refused" cannot tell which of the two did
        # the refusing.
        "cmd_ring": {"id": "cmd_ring", "type": "sequence",
                     "steps": [visit("круг"),
                               {"type": "call", "target": "cmd_ring"}]},
    }
    opened.clear()
    ok, _ = execute({"type": "sequence",
                     "steps": [{"type": "call", "target": "cmd_a"}]},
                    lookup=store.get)
    check("вызов другой команды выполняет её",
          ok and [u.split("//")[-1] for u in opened] == ["из-другой"],
          f"| {opened}")

    # A ring is refused **at the first repeat**, not five levels down.
    #
    # The depth limit stops it either way, which is why the first version of
    # this check passed with the guard removed. What separates them is how
    # far it got: once round with the guard, once per level without it.
    opened.clear()
    ok, _ = execute(store["cmd_ring"], lookup=store.get)
    check("команда не вызывает саму себя по кругу", not ok, f"| ok={ok}")
    # Two rounds, not one: the outermost run is not itself a "call", so the
    # ring is noticed the first time the command is **called** — one round
    # in. Without the guard the depth limit stops it instead, five in.
    check("и останавливается на первом повторе, а не по глубине",
          len(opened) == 2, f"| кругов {len(opened)}")

    # --- asking about the machine ----------------------------------------
    #
    # Through the seam, because the core has no system calls of its own.
    # What is checked is that the answer decides the branch and that a
    # missing answer decides it the safe way.
    asked = []

    def machine(question, about=""):
        asked.append((question, about))
        return "C:/Apps/Chrome/chrome.exe" if question == "foreground" else ""

    opened.clear()
    execute({"type": "if", "condition": "app_active", "value": "chrome",
             "steps": [visit("front")], "otherwise": [visit("not-front")]},
            machine=machine)
    check("условие про открытую программу спрашивает оболочку",
          asked and asked[0][0] == "foreground", f"| {asked}")
    check("и ветвится по её ответу",
          [u.split("//")[-1] for u in opened] == ["front"], f"| {opened}")

    opened.clear()
    execute({"type": "if", "condition": "app_running", "value": "чего-нибудь",
             "steps": [visit("running")], "otherwise": [visit("no")]},
            machine=machine)
    check("а «запущена ли» — по своему",
          [u.split("//")[-1] for u in opened] == ["no"], f"| {opened}")

    # No shell is not "yes". A condition that cannot be established is
    # false, and a command branching on a guess would do the wrong half of
    # itself in silence.
    #
    # Asked through `app_running`, where **any** answer at all flips the
    # branch. The first version asked through `app_active`, which compares
    # the answer with a name: a shell-less "yes" does not contain "chrome",
    # so the branch stayed put and the check passed even with the
    # no-shell-means-no rule removed.
    opened.clear()
    execute({"type": "sequence", "steps": [
        {"type": "if", "condition": "app_running", "value": "chrome",
         "steps": [visit("guessed")], "otherwise": [visit("safe")]},
        {"type": "if", "condition": "app_active", "value": "chrome",
         "steps": [visit("guessed2")], "otherwise": [visit("safe2")]},
    ]})
    check("без оболочки условие о машине ложно",
          [u.split("//")[-1] for u in opened] == ["safe", "safe2"],
          f"| {opened}")


finally:
    user_commands.webbrowser = was


# --- a trial says which step it is on --------------------------------------
#
# Only while somebody is watching. A scenario fired by voice has nobody
# looking at a canvas, and filling the event channel with steps nobody reads
# would be paying for a picture that is not on a screen.
was = user_commands.webbrowser
user_commands.webbrowser = Opener
try:
    told = []
    opened.clear()
    execute({"type": "sequence", "steps": [
        visit("a"),
        {"type": "repeat", "count": 2, "steps": [visit("b")]},
        {"type": "выдумка"},
    ]}, emit=lambda name, **p: told.append((p["path"], p["state"])),
        trace=True)

    check("проба сообщает о каждом шаге", len(told) >= 8, f"| {len(told)}")
    check("путь называет место в дереве, а не порядок вызова",
          ("steps.1.steps.0", "running") in told,
          f"| {[p for p, _ in told]}")
    check("упавший шаг назван упавшим",
          ("steps.2", "failed") in told, f"| {told[-2:]}")

    # And silence when nobody asked. The same run without `trace`.
    quiet = []
    execute({"type": "sequence", "steps": [visit("c")]},
            emit=lambda name, **p: quiet.append(p), trace=False)
    check("без наблюдателя ничего не сообщается", quiet == [], f"| {quiet}")
finally:
    user_commands.webbrowser = was


# --- these kinds are steps, not commands -----------------------------------
#
# A command of type "wait" would do nothing on purpose; one that is only a
# repeat says nothing about what it repeats. The core states this, because
# it is about what they mean.
check("управление потоком объявлено шагами, а не командами",
      user_commands.STEP_ONLY == {"pause", "repeat", "while", "if",
                                  "stop", "call", "set"},
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
