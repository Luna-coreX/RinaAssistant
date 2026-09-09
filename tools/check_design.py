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

# Shadows: named, few, and only what motion needs (the 4.0b-A06 amendment).
#
# The rule used to be "no shadows in the tokens at all", and until 4.0b-A06
# that was the whole of it. The amendment is narrow: a shadow is allowed as
# **movement** — a layer arriving carries one — and under what genuinely
# floats above the window. In a still frame there is still no shadow.
#
# So the check changed its subject rather than went away. Forbidding the
# token would forbid the decision; what has to be forbidden is the cliché,
# and the cliché has a shape: many levels, and a blur wide enough to be a
# separator rather than a hint of travel.
check("размытия как отдельного средства нет", "blur" not in tokens)

lift = tokens.get("elevation") or {}
levels = lift.get("level") or {}
check("уровни возвышения названы поимённо", bool(levels), f"| {sorted(levels)}")

# Three and no more. A fourth level is not distinguishable by a person, and
# an indistinguishable level is decoration — which is what §5 forbids.
check("уровней не больше трёх", len(levels) <= 3, f"| {len(levels)}")

widest = max((spec.get("blur", 0) for spec in levels.values()), default=0)
check("тень не шире 32 — иначе она разделитель, а не признак движения",
      widest <= 32, f"| {widest}")

# Every finish has to say what its shadow is painted with. A shadow without
# a colour of its own would be painted with black on silver too, and that is
# how the cliché starts.
missing = [name for name, finish in tokens["finishes"].items()
           if not finish.get("shadow")]
check("у каждой отделки свой цвет тени", not missing, f"| {missing}")

if mockups:
    # The mock-up is a still frame, and a still frame has no motion in it.
    # So here the old rule holds in full: what is seen in a screenshot is
    # exactly what the amendment did not permit.
    bad = [w for w in ("box-shadow", "text-shadow", "filter: blur",
                       "backdrop-filter")
           if w in mockups]
    check("в макете нет теней и размытий", not bad, f"| {bad}")

# exactly one gradient — the level strip
if mockups:
    gradients = re.findall(r"linear-gradient", mockups)
    # the hatching's repeating-linear-gradient is counted separately
    plain = len(gradients) - mockups.count("repeating-linear-gradient")
    check("градиент ровно один (полоса уровня)", plain == 1, f"| {plain}")

# The living background (`4.0b-A06`): a computed flow, and the rules it
# still has to keep.
#
# The rule "no colour the panel does not have" is gone, and deliberately.
# It was written when the background was a whisper, and the person asked
# for a background one can see — a nebula, not a sheen. A rule kept while
# the thing it described has changed is worse than no rule: it goes green
# on something it was never about.
#
# What replaces it are the limits that still mean something.
def _value(hex_color):
    h = hex_color.lstrip("#")
    return sum(int(h[i:i + 2], 16) for i in (0, 2, 4)) / 3


def _chroma(hex_color):
    h = hex_color.lstrip("#")
    channels = [int(h[i:i + 2], 16) for i in (0, 2, 4)]
    return (max(channels) - min(channels)) / 255


for name, finish in tokens["finishes"].items():
    nebula = finish.get("nebula")
    if not nebula:
        check(f"[{name}] живой фон задан", False)
        continue

    ramp = nebula["ramp"]

    # Enough stops for a flow, few enough to stay one colour's story. Two
    # would be a gradient; a dozen would be a rainbow.
    check(f"[{name}] ступеней от трёх до семи", 3 <= len(ramp) <= 7,
          f"| {len(ramp)}")

    # Monotone in value. A ramp that rises and falls puts a hard line
    # wherever it turns, and the flow would show a contour where the
    # mathematics is smooth.
    values = [_value(stop) for stop in ramp]
    rising = all(b >= a for a, b in zip(values, values[1:]))
    falling = all(b <= a for a, b in zip(values, values[1:]))
    check(f"[{name}] палитра идёт в одну сторону", rising or falling,
          f"| {[round(v) for v in values]}")

    # Not fluorescent. The nebula may be coloured — that is the point — but
    # a channel spread past a quarter of the range stops being a lit panel
    # and becomes a screensaver.
    worst = max(_chroma(stop) for stop in ramp)
    check(f"[{name}] цвет насыщенный, но не люминесцентный", worst <= 0.25,
          f"| {worst * 100:.1f}% (не больше 25)")

    # The field's own parameters. Warp is what makes it liquid rather than
    # cloudy; without any it is fog, and far past one it tears.
    check(f"[{name}] искажение области в деле",
          0.3 <= nebula["warp"] <= 2.0, f"| {nebula['warp']}")
    check(f"[{name}] крупность поля разумна",
          1.0 <= nebula["scale"] <= 8.0, f"| {nebula['scale']}")

# Typography: a role that names a family must have that family applied.
#
# Every role has named one since `4.0-R03`, and until `4.0b-A06` nothing
# read it: every style inherited the single UI face, so `"family":
# "display"` was a word in a file. The role `value` went further — it was
# described, emitted, and had no style at all, so nothing in the window
# could ask for it.
#
# Both are the same failure and it is the quiet kind: the tokens look like a
# decision, the window looks finished, and the two have nothing to do with
# each other.
print()
print("=== роли текста применены, а не только объявлены ===")

STYLES = os.path.join(ROOT, "shell", "Rina.Shell", "Styles", "Text.xaml")
GENERATED = os.path.join(ROOT, "shell", "Rina.Shell", "Generated",
                         "Tokens.g.xaml")
with open(STYLES, encoding="utf-8") as handle:
    styles = handle.read()
with open(GENERATED, encoding="utf-8") as handle:
    generated = handle.read()

for role, spec in tokens["typography"]["role"].items():
    name = role.capitalize()
    check(f"роль {role}: семейство отдано в ресурсы",
          f'x:Key="Type.{name}.Family"' in generated)
    check(f"роль {role}: у неё есть стиль",
          f'x:Key="Text.{name}"' in styles)
    check(f"роль {role}: стиль применяет её семейство",
          f"Type.{name}.Family" in styles)

# And nothing declares what cannot be carried out. WPF has no letter spacing
# on a TextBlock; a `tracking` in the tokens would be a number that looks
# like a decision and is a note.
for role, spec in tokens["typography"]["role"].items():
    check(f"роль {role}: не обещает невыполнимого",
          "tracking" not in spec, "| WPF не умеет межбуквенный интервал")


# The finishes are equal (`4.0-R08`), and "equal" is a checkable statement:
# the same set of roles, and glass that is dark in every one of them.
#
# It used to name `silver` and `black` by hand. That held while there were
# two of them and stopped holding the moment `graphite` arrived in
# `4.0b-A06`: the third finish would have gone unchecked, and unchecked in
# silence, because a check that names two names cannot notice a third.
print(f"=== R08: отделок {len(tokens['finishes'])}, и они равноправны ===")

roles = {name: set(finish["color"])
         for name, finish in tokens["finishes"].items()}
first = next(iter(roles))
for name, keys in roles.items():
    if name == first:
        continue
    check(f"[{name}] набор ролей тот же, что у «{first}»", keys == roles[first],
          f"| только в одной: {keys ^ roles[first]}")

for name, finish in tokens["finishes"].items():
    # Glass is where Rina's voice appears, and it is dark in every finish:
    # "silver" is a finish of the panel, not of the screen.
    glass = finish["color"]["GLASS"].lstrip("#")
    value = sum(int(glass[i:i + 2], 16) for i in (0, 2, 4)) / 3
    check(f"[{name}] стекло тёмное", value < 0x40, f"| {value:.0f} из 255")

print()
print("ИТОГО ошибок:", fails)
sys.exit(1 if fails else 0)
