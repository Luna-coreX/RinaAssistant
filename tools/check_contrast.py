# -*- coding: utf-8 -*-
"""
Проверка контраста токенов (задача плана 4.0-R03).

Палитру нельзя утверждать на веру: «выглядит читаемо» на мониторе автора и
«читаемо» — разные утверждения. Здесь считается контраст по WCAG 2.1 для
каждой пары «текст на поверхности», которая встречается в системе.

Пороги:
    4.5   обычный текст
    3.0   крупный текст (от 18 px, либо от 14 px полужирный) и границы
          управляющих элементов

Отключённое состояние по стандарту от требований освобождено, но и оно
проверяется на 3.0: «выключено» должно читаться как выключенное, а не как
отсутствующее.

Запуск:
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


#: (текст, поверхность, порог, за что отвечает)
PAIRS = (
    ("INK",        "FACE",       4.5, "основной текст на панели"),
    ("INK",        "FACE_HIGH",  4.5, "текст на приподнятой секции"),
    ("INK",        "FACE_LOW",   4.5, "текст на утопленной секции"),
    ("INK_SOFT",   "FACE",       4.5, "легенды органов управления"),
    ("INK_SOFT",   "FACE_HIGH",  4.5, "легенды на приподнятом"),
    ("INK_FAINT",  "FACE",       3.0, "выключенное состояние"),
    # Недоступный вариант в раскрытом списке. Он показан нарочно — человек
    # должен видеть, что такой движок бывает, — и потому обязан читаться,
    # а не сливаться с подложкой. На утопленной подложке в «серебре» выходило
    # 2.90, поэтому список лежит на приподнятой: это и семантически верно —
    # всплывающее окно поверх панели, а не углубление в ней.
    ("INK_FAINT",  "FACE_HIGH",  3.0, "недоступный вариант в списке"),
    ("GLASS_TEXT", "GLASS",      4.5, "реплики на стекле"),
    ("GLASS_DIM",  "GLASS",      4.5, "время и служебное на стекле"),
    ("SIGNAL",     "FACE",       4.5, "признак ошибки — это текст, не рамка"),
    ("SIGNAL",     "FACE_HIGH",  3.0, "рамка фокуса на приподнятом"),
    ("FACE",       "INK",        4.5, "первичная кнопка: панель на чернилах"),
    ("SEAM",       "FACE",       1.2, "волосяной шов между областями"),
)


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

    print(f"\nПар проверено: {len(PAIRS) * len(tokens['finishes'])}, "
          f"недостаточных: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
