# -*- coding: utf-8 -*-
"""
Checking the tokens' contrast (plan item 4.0-R03).

A palette must not be approved on trust: "looks readable" on the author's
monitor and "readable" are different statements. Here the WCAG 2.1 contrast
is computed for every "text on a surface" pair that occurs in the system.

The thresholds:
    4.5   ordinary text
    3.0   large text (from 18 px, or from 14 px bold) and the borders of
          controls

A disabled state is exempt from the requirements by the standard, but it is
checked against 3.0 all the same: "off" must read as switched off rather
than as missing.

To run:
    python tools/check_contrast.py
"""

import json
import os
import sys

from console import use_utf8

use_utf8()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOKENS = os.path.join(ROOT, "docs", "design", "tokens.json")


def _channel(value):
    value /= 255.0
    return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4


def luminance(hex_color):
    hex_color = hex_color.lstrip("#")
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
    return (0.2126 * _channel(r) + 0.7152 * _channel(g)
            + 0.0722 * _channel(b))


def contrast(a, b):
    la, lb = luminance(a), luminance(b)
    lighter, darker = max(la, lb), min(la, lb)
    return (lighter + 0.05) / (darker + 0.05)


#: (text, surface, threshold, what it is responsible for)
PAIRS = (
    ("INK",        "FACE",       4.5, "основной текст на панели"),
    ("INK",        "FACE_HIGH",  4.5, "текст на приподнятой секции"),
    ("INK",        "FACE_LOW",   4.5, "текст на утопленной секции"),
    ("INK_SOFT",   "FACE",       4.5, "легенды органов управления"),
    ("INK_SOFT",   "FACE_HIGH",  4.5, "легенды на приподнятом"),
    ("INK_FAINT",  "FACE",       3.0, "выключенное состояние"),
    # An unavailable option in an opened list. It is shown deliberately — a
    # person must see that such an engine exists — and so is obliged to read
    # rather than merge with the ground. On the sunk ground in "silver" it
    # came out at 2.90, so the list lies on the raised one: that is
    # semantically right too — a popup above the panel, not a hollow in it.
    ("INK_FAINT",  "FACE_HIGH",  3.0, "недоступный вариант в списке"),
    ("GLASS_TEXT", "GLASS",      4.5, "реплики на стекле"),
    ("GLASS_DIM",  "GLASS",      4.5, "время и служебное на стекле"),
    ("SIGNAL",     "FACE",       4.5, "признак ошибки — это текст, не рамка"),
    ("SIGNAL",     "FACE_HIGH",  3.0, "рамка фокуса на приподнятом"),
    ("FACE",       "INK",        4.5, "первичная кнопка: панель на чернилах"),
    ("SEAM",       "FACE",       1.2, "волосяной шов между областями"),
)


def check_accents(tokens, report):
    """
    Every accent is checked in the same place the original was.

    Choosing a colour must not be a way of making a sign of error
    unreadable. So an unchecked accent does not get into the set: an accent
    has exactly two duties — to read on the panel and to read on the raised
    surface — and both are checked for **every** variant, not for whichever
    is set right now.
    """
    failures = 0
    for key, finish in tokens["finishes"].items():
        colors = finish["color"]
        for name, accent in (finish.get("accents") or {}).items():
            for surface, need in (("FACE", 4.5), ("FACE_HIGH", 3.0)):
                value = contrast(accent["signal"], colors[surface])
                ok = value >= need
                failures += 0 if ok else 1
                report(f"{key}/{name}: акцент на {surface.lower()}",
                       ok, f"{value:.2f} (нужно {need})")
    return failures


def main():
    tokens = json.load(open(TOKENS, encoding="utf-8"))
    failures = 0

    for key, finish in tokens["finishes"].items():
        colors = finish["color"]
        print(f"\n=== отделка «{finish['title']}» ===")
        for text, surface, threshold, what in PAIRS:
            ratio = contrast(colors[text], colors[surface])
            ok = ratio >= threshold
            if not ok:
                failures += 1
            mark = "OK  " if ok else "МАЛО"
            print(f"  {mark} {ratio:5.2f} (нужно {threshold:.1f})  "
                  f"{text} на {surface:<10} — {what}")

    def report(label, ok, detail):
        print(f"  {'OK  ' if ok else 'МАЛО'} {detail:>22}  {label}")

    accents = sum(len(f.get("accents") or {})
                  for f in tokens["finishes"].values())
    if accents:
        print()
        print(f"Акценты ({accents} шт.):")
        failures += check_accents(tokens, report)

    print(f"\nПар проверено: {len(PAIRS) * len(tokens['finishes'])} "
          f"+ акцентов {accents * 2}, "
          f"недостаточных: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
