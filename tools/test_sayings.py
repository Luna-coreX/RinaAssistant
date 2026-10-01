# -*- coding: utf-8 -*-
"""
Several ways to say one thing (`core/sayings.py`).

Asked for by a person (2026-10-02): the same «Дел нет» every time sounds
like a table. Checked here:

- every variant of a saying takes the same values — a variant asking for
  `{text}` where its siblings ask for `{count}` would fail on one answer in
  three;
- the pick never repeats the variant said last, and over time every variant
  is said;
- with plain speech — what every other check hears — the first variant,
  always;
- every saying the code asks for exists, and none sits unused.

To run:
    python tools/test_sayings.py
"""
import io
import os
import random
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

from console import use_utf8

use_utf8()

from core import sayings

fails = 0


def check(label, cond, detail=""):
    global fails
    if not cond:
        fails += 1
    print(("OK   " if cond else "FAIL "), label, detail)


def holes(text):
    return set(re.findall(r"\{(\w+)\}", text))


print("=== варианты одной фразы берут одни и те же значения ===")
uneven = [key for key, variants in sayings.SAYINGS.items()
          if len({frozenset(holes(v)) for v in variants}) != 1]
check("подстановки у вариантов совпадают", not uneven, f"| {uneven}")
check("у частых фраз больше одного варианта",
      all(len(sayings.SAYINGS[key]) > 1 for key in
          ("todo.none", "todo.added", "clock.time", "answer.hello",
           "answer.thanks", "timer.set", "calc")))

print()
print("=== выбор ===")
sayings.PLAIN = True
check("в проверках — всегда первый вариант",
      {sayings.say("todo.none") for _ in range(10)}
      == {sayings.SAYINGS["todo.none"][0]})

sayings.PLAIN = False
random.seed(20261002)
heard = [sayings.say("todo.none") for _ in range(60)]
check("один вариант не звучит дважды подряд",
      all(a != b for a, b in zip(heard, heard[1:])), f"| {heard[:6]}")
check("со временем звучат все варианты",
      set(heard) == set(sayings.SAYINGS["todo.none"]), f"| {set(heard)}")
filled = sayings.say("todo.added", text="купить хлеб")
check("и значение подставлено", "купить хлеб" in filled and "{" not in filled,
      f"| {filled}")
sayings.PLAIN = None

print()
print("=== каталог и код согласны ===")
asked = set()
for base, dirs, files in os.walk(ROOT):
    dirs[:] = [d for d in dirs if d not in {".git", "venv", "__pycache__",
                                            "archive", ".claude", "dist",
                                            "build", "shell", "tools"}]
    for name in files:
        if name.endswith(".py"):
            text = io.open(os.path.join(base, name), encoding="utf-8").read()
            # `saying(` too: the clock has a `say` of its own and imports
            # the catalogue's under that name.
            asked |= set(re.findall(r'\b(?:say|saying)\(\s*f?"([\w.]+)"',
                                    text))
            # The system's sayings are asked for by name built from the
            # action: `say(f"system.{action_id}")`.
            if 'say(f"system.{action_id}")' in text:
                asked |= {k for k in sayings.SAYINGS if k.startswith("system.")}
missing = sorted(asked - set(sayings.SAYINGS))
unused = sorted(set(sayings.SAYINGS) - asked)
check("каждая фраза, которую зовёт код, есть в каталоге", not missing,
      f"| нет: {missing}")
check("и в каталоге нет фраз, которых никто не зовёт", not unused,
      f"| лишние: {unused}")

print()
print("ИТОГО ошибок:", fails)
sys.exit(1 if fails else 0)
