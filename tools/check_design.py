# -*- coding: utf-8 -*-
"""
Comparing the design with the surface inventory and with the direction.

Plan item 4.0-R11. An interface has no equivalent of the golden suite: after
a redesign everything differs deliberately, and there is nothing to tell
"that was intended" from "we lost it" automatically. This comparison plays
the part of the criterion.

Two things are checked:

    1. Every action from the surface inventory's "Available only from here"
       section has an address in the new information architecture. A lost
       button is a lost capability, and the core will not learn of it: the
       golden suite checks the core, not the window.

    2. The tokens and the layout answer "no" to the twelve questions of the
       direction. The system is built so that honestly following it gives
       that automatically; the check catches the departures.

To run:
    python tools/check_design.py
"""

import json
import os
import re
import sys

from console import use_utf8

use_utf8()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SURFACE = os.path.join(ROOT, "docs", "SURFACE-3.1.0.md")
IA = os.path.join(ROOT, "docs", "design", "IA.md")
TOKENS = os.path.join(ROOT, "docs", "design", "tokens.json")
MOCKUPS = os.path.join(ROOT, "docs", "design", "mockups.html")

fails = 0


def check(label, cond, detail=""):
    global fails
    if not cond:
        fails += 1
    print(("OK   " if cond else "FAIL "), label, detail)


def read(path):
    return open(path, encoding="utf-8").read()


# ---------------------------------------------------------------------------
# 1. Every action has an address
# ---------------------------------------------------------------------------
def only_here_actions():
    """The rows of the "Available only from here" table from the surface inventory."""
    text = read(SURFACE)
    start = text.index("## 3. Доступно только отсюда")
    end = text.index("## 4.", start)
    rows = []
    for line in text[start:end].split("\n"):
        if not line.startswith("|") or line.startswith("|---"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 2 or cells[0].startswith("Действие"):
            continue
        rows.append((cells[0], cells[1]))
    return rows


#: Where each 3.1.0 screen moved to. The key is what the section was called in the inventory.
HOMES = {
    "Команды": "Команды",
    "История": "Диалог",
    "Плагины": "Плагины",
    "Рина": "Настройки",
    "Настройки": "Настройки",
    "Горячие клавиши": "Настройки",
    "Заголовок окна": "каркас окна",
}

print("=== R11: каждое действие имеет адрес ===")
actions = only_here_actions()
check("таблица инвентаря прочитана", len(actions) >= 20,
      f"| строк: {len(actions)}")

ia = read(IA)
ia_low = ia.lower()
homeless = []
for action, address in actions:
    # An address is sometimes compound: "Настройки → Голос" and "Настройки, Рина".
    screens = [part.strip()
               for chunk in address.split("→")[0].split(",")
               for part in [chunk] if part.strip()]
    homes = [HOMES.get(sc) for sc in screens]
    if not any(homes):
        homeless.append(f"{action} (экраны {screens} не отображены)")
        continue
    for home in homes:
        if home and home.lower() not in ia_low:
            homeless.append(f"{action} → раздел «{home}» отсутствует в ИА")

check("все действия нашли раздел", not homeless, f"| {homeless}")
print(f"     проверено действий: {len(actions)}, "
      f"разделов назначения: {len(set(HOMES.values()))}")

print()
print("=== R11: перечисленные разделы существуют ===")
SECTIONS = ("Диалог", "Команды", "Напоминания", "Плагины", "Настройки")
for name in SECTIONS:
    check(f"раздел «{name}» объявлен", f"**{name}**" in ia or f"| **{name}**" in ia)

print()
print("=== направление: двенадцать вопросов ===")
tokens = json.load(open(TOKENS, encoding="utf-8"))
mockups = read(MOCKUPS) if os.path.isfile(MOCKUPS) else ""

# the radius
check("радиус не больше 3",
      max(tokens["radius"].values()) <= 3, f"| {tokens['radius']}")

# ...and not only in the tokens. The first edition looked here and was green
# while the markup held a toggle with a radius of 11: the rule was guarded at
# the source and broken at the consumer.
LIMIT = max(tokens["radius"].values())
SHELL = os.path.join(ROOT, "shell", "Rina.Shell")
too_round = []
for base, dirs, files in os.walk(SHELL):
    dirs[:] = [d for d in dirs if d not in ("obj", "bin", "Generated")]
    for name in files:
        if not name.endswith((".xaml", ".cs")):
            continue
        path = os.path.join(base, name)
        text = read(path)
        for number, line in enumerate(text.split("\n"), 1):
            for found in re.findall(r'CornerRadius="([0-9]+)"', line):
                if int(found) > LIMIT:
                    too_round.append(f"{name}:{number} = {found}")
            for found in re.findall(r"CornerRadius\((\d+)", line):
                if int(found) > LIMIT:
                    too_round.append(f"{name}:{number} = {found}")

check("и в разметке с кодом тоже", not too_round,
      f"| {too_round}" if too_round else f"| предел {LIMIT}")

# one accent
for key, finish in tokens["finishes"].items():
    colors = finish["color"]
    accents = [k for k in colors if k.startswith("SIGNAL")]
    check(f"[{key}] акцент один (плюс его нажатое состояние)",
          set(accents) == {"SIGNAL", "SIGNAL_SUNK"}, f"| {accents}")

# there is no red
def is_reddish(hex_color):
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return r > 150 and g < 60 and b < 60

for key, finish in tokens["finishes"].items():
    reds = [k for k, v in finish["color"].items() if is_reddish(v)]
    check(f"[{key}] красного в палитре нет", not reds, f"| {reds}")

# danger by hatching
check("опасность обозначена штриховкой",
      tokens["states"]["danger"].get("hatch") is True
      and "hatch" in tokens)
check("у ошибки и опасности разные средства",
      tokens["states"]["error"].get("hatch") is not True)

# no shadows and no blurs
check("в токенах нет теней и размытий",
      not any(k in tokens for k in ("shadow", "blur", "elevation")))
if mockups:
    bad = [w for w in ("box-shadow", "text-shadow", "filter: blur", "backdrop-filter")
           if w in mockups]
    check("в макете нет теней и размытий", not bad, f"| {bad}")

# exactly one gradient — the level strip
if mockups:
    gradients = re.findall(r"linear-gradient", mockups)
    # the hatching's repeating-linear-gradient is counted separately
    plain = len(gradients) - mockups.count("repeating-linear-gradient")
    check("градиент ровно один (полоса уровня)", plain == 1, f"| {plain}")

# tabular figures
check("цифры моноширинные",
      tokens["typography"]["role"]["figure"]["family"] == "mono"
      and tokens["typography"]["role"]["figure"].get("tabular") is True)

# the afterglow
check("состояние гаснет, а не переключается",
      tokens["motion"]["afterglow"] >= 500,
      f"| {tokens['motion']['afterglow']} мс")

# --- motion is declared and **applied** --------------------------------------
#
# A token nobody uses is an intention rather than a decision. The motion
# system (SYSTEM §7) was generated into `Motion.*` and used nowhere: states
# switched instantly, and the level strip jumped between zero and forty per
# cent. The twelve questions of the direction call that a plain "not in the
# style", and a check on the tokens did not catch it — the value was in the
# file, after all.
SHELL = os.path.join(ROOT, "shell", "Rina.Shell")
used = []
for base, dirs, files in os.walk(SHELL):
    dirs[:] = [d for d in dirs if d not in ("obj", "bin", "Generated")]
    for name in files:
        if name.endswith((".xaml", ".cs")):
            used.append(read(os.path.join(base, name)))
code = chr(10).join(used)

for name in ("Press", "State", "Panel", "Afterglow"):
    applied = f"Motion.{name}" in code
    check(f"длительность {name} применена, а не только объявлена", applied,
          "" if applied else "| токен без применения — намерение, а не решение")

on_strip = "Motion.Afterglow" in read(os.path.join(SHELL, "MainWindow.xaml.cs"))
check("послесвечение висит на полосе уровня", on_strip,
      "" if on_strip else "| «полоса не переключается между выключено и "
                          "включено» (DIRECTION §4)")

# the gap around the dangerous is twice the usual
check("опасное отделено пустотой",
      tokens["space"]["danger"] >= tokens["space"]["between"] * 2,
      f"| {tokens['space']['danger']} против {tokens['space']['between']}")

print()
print("=== R08: две отделки равноправны ===")
silver = set(tokens["finishes"]["silver"]["color"])
black = set(tokens["finishes"]["black"]["color"])
check("набор ролей совпадает", silver == black,
      f"| только в одной: {silver ^ black}")
check("стекло в обеих отделках тёмное",
      tokens["finishes"]["silver"]["color"]["GLASS"].lower() < "#404040"
      and tokens["finishes"]["black"]["color"]["GLASS"].lower() < "#404040")

print()
print("ИТОГО ошибок:", fails)
sys.exit(1 if fails else 0)
