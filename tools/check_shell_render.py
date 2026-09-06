# -*- coding: utf-8 -*-
"""
Comparing the drawn window with the tokens — by pixels.

Plan item 4.0-F03.

"Looks like the mockup" is not a check. The window is drawn by WPF, the
styles are written by a person, the values come from `tokens.json`, and they
can part company in any of the three places: a typo in a resource key, a
forgotten `DynamicResource`, a style that did not apply. Not one of those
divergences is noticeable by eye — a colour that is "about right" looks like
the right colour.

So the shell can draw itself into a PNG (`--shot`), and here the screenshot
is taken apart point by point: the column of sections, the panel, the mark
of the active section, the level strip, the title bar. Exactly those places
where a value is obliged to match a token.

What is checked is **what was drawn**, not the markup: the markup can be
read with one's eyes, and it says nothing about what came out on the screen
anyway.

To run (the shell takes the screenshots itself):
    dotnet run --project shell/Rina.Shell -- --shot silver.png --finish silver
    python tools/check_shell_render.py silver.png silver
"""

import json
import os
import sys

from console import use_utf8

use_utf8()

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOKENS = os.path.join(ROOT, "docs", "design", "tokens.json")

fails = 0


def check(label, cond, detail=""):
    global fails
    if not cond:
        fails += 1
    print(("OK   " if cond else "FAIL "), label, detail)


def rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def near(a, b, tolerance=2) -> bool:
    """A match with a tolerance: edge antialiasing changes a point by one."""
    return all(abs(x - y) <= tolerance for x, y in zip(a[:3], b))


def check_confirm(image, colors, tokens) -> int:
    """
    The confirmation window (4.0-F11): danger by hatching, not by colour.

    The hatching is found by the spread of brightness in the button's band:
    a pattern is an alternation, and on an even fill there will be no
    spread. Looking for a particular point of the pattern would mean
    checking where exactly a line fell rather than that the pattern is
    there.
    """
    width, height = image.size
    print(f"=== F11: окно подтверждения, {width}x{height} ===")

    check("окно на панели, а не на системном фоне",
          near(image.getpixel((width // 2, 8)), colors["FACE"]),
          f"| {image.getpixel((width // 2, 8))}")

    # The band where the button of the irreversible stands.
    row = int(height * 0.66)
    strip = [image.getpixel((x, row)) for x in range(24, 170)]
    greys = sorted({p[0] for p in strip})
    check("кнопка необратимого заштрихована",
          len(greys) >= 3 and max(greys) - min(greys) > 20,
          f"| оттенков {len(greys)}, размах {max(greys) - min(greys)}")

    # `getdata` is declared for removal in Pillow 14. The same case as
    # `audioop` in the core: learning of it while upgrading the library is
    # the worst moment, and `getcolors` does exactly what is needed and
    # counts the points into the bargain.
    everything = {colour for _, colour in image.getcolors(1 << 24)}
    reds = [p for p in everything if p[0] > 150 and p[1] < 60 and p[2] < 60]
    check("красного нет нигде", not reds, f"| {reds[:3]}")

    check("акцент есть — это рамка фокуса на отказе",
          any(near(p, colors["SIGNAL"], 24) for p in everything))

    # The gap around the irreversible is twice the usual (§4).
    gap = tokens["space"]["danger"]
    check("просвет вокруг необратимого объявлен вдвое большим",
          gap >= tokens["space"]["between"] * 2, f"| {gap}")

    # The sample's upper bound must not touch the button itself: it is a
    # control's height, and half of it lies above the middle of the row.
    control = int(tokens["size"]["control"])
    above = [image.getpixel((60, y))
             for y in range(row - gap + 8, row - control // 2 - 4)]
    check("над кнопкой действительно пусто",
          all(near(p, colors["FACE"], 3) for p in above),
          f"| {sorted(set(above))} в просвете")

    print()
    print("ИТОГО ошибок:", fails)
    return 1 if fails else 0


def main(argv) -> int:
    if len(argv) < 2:
        print("нужно: путь-к-снимку отделка")
        return 2
    path, finish_name = argv[0], argv[1]

    with open(TOKENS, encoding="utf-8") as f:
        tokens = json.load(f)
    colors = {k: rgb(v)
              for k, v in tokens["finishes"][finish_name]["color"].items()}
    size = tokens["size"]

    image = Image.open(path).convert("RGB")
    width, height = image.size

    if len(argv) > 2 and argv[2] == "confirm":
        return check_confirm(image, colors, tokens)
    print(f"=== F03: {os.path.basename(path)}, отделка «{finish_name}», "
          f"{width}x{height} ===")

    def at(x, y):
        return image.getpixel((int(x), int(y)))

    # The column of sections is sunk relative to the panel: that is a step of
    # value, the system's only means of raising something (there are no
    # shadows).
    column = size["legend_column"]
    # The column's background is measured at its right edge rather than in
    # the middle: in the middle lie the sections' names, and a point lands in
    # a letter. An antialiased letter is neither background nor ink but
    # something between, and the check would catch it.
    inside = column - 8
    check("колонка разделов — FACE_LOW",
          near(at(inside, height * 0.55), colors["FACE_LOW"]),
          f"| {at(inside, height * 0.55)} против {colors['FACE_LOW']}")
    # The panel is measured in the field between the column and the
    # section's contents rather than in the middle of it: it used to be empty
    # there, and with the pages appearing, a glass field lies in the middle
    # of a section — and the check would catch the contents, passing that off
    # as a broken frame.
    pane_margin = column + tokens["space"]["between"] / 2
    check("панель раздела — FACE",
          near(at(pane_margin, height * 0.5), colors["FACE"]),
          f"| {at(pane_margin, height * 0.5)} против {colors['FACE']}")
    check("полоса заголовка — FACE_LOW",
          near(at(width * 0.5, size["row"] / 2), colors["FACE_LOW"]),
          f"| {at(width * 0.5, size['row'] / 2)}")

    # The mark of the active section is the system's only accent. Which
    # section is open the check does not know and must not know: it finds the
    # mark itself. Tying it to the first section would make it a check of a
    # screenshot rather than a check of a rule.
    row = size["row"]
    marked = [y for y in range(size["row"], height - size["level_strip"])
              if near(at(1, y), colors["SIGNAL"], 6)]
    check("активный раздел отмечен акцентом", marked,
          f"| точек акцента: {len(marked)}")

    if marked:
        runs = []
        start = previous = marked[0]
        for y in marked[1:]:
            if y != previous + 1:
                runs.append((start, previous))
                start = y
            previous = y
        runs.append((start, previous))
        check("отметка одна", len(runs) == 1, f"| {runs}")

        top, bottom = runs[0]
        middle = (top + bottom) // 2
        check("высота отметки — в строку раздела",
              abs((bottom - top + 1) - row) <= 1, f"| {bottom - top + 1}")
        check("акцент шириной ровно 2 точки",
              not near(at(4, middle), colors["SIGNAL"], 6),
              f"| точка 4: {at(4, middle)}")
        check("активный раздел заподлицо с панелью",
              near(at(inside, middle), colors["FACE"]),
              f"| {at(inside, middle)}")

        other = middle + row if bottom + row < height * 0.7 else middle - row
        check("неактивный раздел остаётся утопленным",
              near(at(inside, other), colors["FACE_LOW"]),
              f"| {at(inside, other)}")

    # The level strip along the bottom edge of the whole window: the
    # microphone belongs to the instrument as a whole, not to the current
    # section.
    strip = size["level_strip"]
    bottom = at(width * 0.5, height - 2)
    check("полоса уровня по нижней кромке — FACE_SUNK",
          near(bottom, colors["FACE_SUNK"]),
          f"| {bottom} против {colors['FACE_SUNK']}")
    check("полоса уровня во всю ширину",
          near(at(4, height - 2), colors["FACE_SUNK"])
          and near(at(width - 4, height - 2), colors["FACE_SUNK"]),
          f"| слева {at(4, height - 2)}, справа {at(width - 4, height - 2)}")
    check("полоса не толще положенного",
          not near(at(width * 0.5, height - strip - 4), colors["FACE_SUNK"]),
          f"| над полосой: {at(width * 0.5, height - strip - 4)}")

    # There are no shadows: above the column there must be no gradient to dark.
    edge = [at(column + d, height * 0.4) for d in (1, 3, 6, 10)]
    check("между колонкой и панелью нет тени",
          all(near(p, colors["FACE"], 3) for p in edge), f"| {edge}")

    # --- F12: the link's state is visible and coloured correctly ----------
    # It is checked over the whole footer area rather than by a single point:
    # the text is antialiased, and hitting a letter's stroke with a point is
    # checking luck rather than colour.
    if len(argv) > 2:
        wanted_state = argv[2]
        footer = image.crop((0, int(height * 0.86), int(size["legend_column"]),
                             height - size["level_strip"]))
        painted = set(footer.getdata())

        def has(colour, tolerance=24):
            return any(near(p, colour, tolerance) for p in painted)

        if wanted_state == "failed":
            check("неполадка окрашена акцентом", has(colors["SIGNAL"]),
                  f"| акцент {colors['SIGNAL']} среди {len(painted)} оттенков")
        else:
            check("спокойное состояние акцентом не кричит",
                  not has(colors["SIGNAL"], 12),
                  "| акцент в подвале быть не должен")

        # There is no red in the palette at all: the colour of danger wears
        # out through repetition, and a fault is not a danger.
        reds = [p for p in painted if p[0] > 150 and p[1] < 60 and p[2] < 60]
        check("красного в подвале нет", not reds, f"| {reds[:3]}")

    print()
    print("ИТОГО ошибок:", fails)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
