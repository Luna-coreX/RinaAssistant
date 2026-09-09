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


def average(image, x, y, reach=24):
    """
    The average colour of a vertical strip — instead of one point.

    A point on the panel is no longer the panel's colour: over the patches
    of the living background lies a grain of about one value
    (`4.0b-A06`, and it is there to stop the patches banding). On a single
    pixel that grain swings the reading by six, and the check read that as
    a shadow at the seam — the profile came out 33, 39, 33, 33, 39, which
    is not a gradient at all but noise.

    The grain has a mean of zero, so it cancels over a strip. Vertical, and
    not a square: a square near a boundary would take in the neighbouring
    surface, and boundaries are exactly what is measured here.
    """
    reds, greens, blues = [], [], []
    for step in range(-reach, reach + 1):
        pixel = image.getpixel((int(x), int(y) + step))[:3]
        reds.append(pixel[0])
        greens.append(pixel[1])
        blues.append(pixel[2])
    return (sum(reds) / len(reds), sum(greens) / len(greens),
            sum(blues) / len(blues))


def hex_rgb(value):
    """
    A colour as three numbers, however it arrived.

    Both forms occur here and they look alike at the call site: the palette
    out of the tokens is `#1d2022`, and `colors` in this file already holds
    tuples. Taking only one of them made this raise twice in a row on the
    same line — which is exactly the sort of thing that is faster to allow
    than to keep remembering.
    """
    if not isinstance(value, str):
        return tuple(value[:3])
    head = value.lstrip("#")
    return tuple(int(head[at:at + 2], 16) for at in (0, 2, 4))


def brightness(pixel) -> float:
    """How light a point is. Enough for a step of value; not a colour space."""
    return sum(pixel[:3]) / 3


def _tokens():
    with open(TOKENS, encoding="utf-8") as handle:
        return json.load(handle)


def nebula_ramp(finish_name, calm=False):
    """
    The colours the living background can actually show here.

    Not the raw ramp out of the tokens: that one is a neutral ladder, and
    what reaches the screen is that ladder carrying the accent, and — under
    the part one reads — calmed as well. Both are worked out by
    `tools/nebula.py`, the same module the generator uses, so the check and
    the shell cannot drift apart while both look right.
    """
    import nebula

    tokens = _tokens()
    finish = tokens["finishes"][finish_name]
    accent = tokens.get("default_accent", "amber")
    signal = finish["accents"][accent]["signal"]
    spec = finish["nebula"]

    ramp = nebula.tinted(spec["ramp"], signal, spec.get("accent", 0.0))
    if calm:
        ramp = nebula.dimmed(ramp, finish["color"]["FACE"], spec.get("dim", 0))
    return ramp


def glass_over(surface, share, ramp):
    """
    What a pane of glass shows when the flow runs behind it.

    Exactly computable, which is the point. The bars stopped being flat
    surfaces in `4.0b-A06` — they are the finish's own colour at less than
    full strength over the living background — and the check that used to
    demand a flat colour was not wrong about the colour, it was wrong about
    what the thing is. So it now computes the composite instead of widening
    a tolerance until the old assertion stops complaining. A tolerance wide
    enough to swallow the flow would swallow the difference between
    `FACE_LOW` and `FACE_SUNK` as well.
    """
    front = hex_rgb(surface)
    return [tuple(front[c] * share + hex_rgb(under)[c] * (1 - share)
                  for c in range(3))
            for under in ramp]


def _to_segment(point, start, end):
    """How far a colour is from the line between two colours."""
    span = [b - a for a, b in zip(start, end)]
    length = sum(c * c for c in span)
    if length <= 0:
        return max(abs(p - a) for p, a in zip(point, start))
    along = sum((p - a) * c for p, a, c in zip(point, start, span)) / length
    along = max(0.0, min(1.0, along))
    return max(abs(p - (a + c * along))
               for p, a, c in zip(point, start, span))


def off_ramp(pixel, candidates):
    """
    How far a point is from the whole run of colours, not from its stops.

    The flow is continuous: between two stops of the ramp every colour on
    the way between them occurs. Measuring only against the stops would
    call a perfectly ordinary point wrong for the crime of lying halfway.
    """
    point = tuple(pixel[:3])
    if len(candidates) == 1:
        return max(abs(p - c) for p, c in zip(point, candidates[0]))
    return min(_to_segment(point, a, b)
               for a, b in zip(candidates, candidates[1:]))


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
    # The bars stopped being flat surfaces in `4.0b-A06`: each is the
    # finish's own colour at less than full strength over the living
    # background. So the expected value is computed rather than typed —
    # `glass_over` composites the declared surface at the declared share
    # over every colour the flow can reach, and the point has to lie on that
    # run. Widening the old tolerance instead would have swallowed the
    # difference between `FACE_LOW` and `FACE_SUNK` along with the flow.
    glass = _tokens().get("glasswork") or {}
    calm_ramp = nebula_ramp(finish_name, calm=True)
    vivid_ramp = nebula_ramp(finish_name)

    column_glass = glass_over(colors["FACE_LOW"], glass.get("column", 1.0),
                              calm_ramp)
    column_at = at(inside, height * 0.55)
    check("колонка разделов — FACE_LOW сквозь стекло",
          off_ramp(column_at, column_glass) <= 10,
          f"| {column_at}, расходится на "
          f"{off_ramp(column_at, column_glass):.0f}")
    # The panel is measured in the field between the column and the
    # section's contents rather than in the middle of it: it used to be empty
    # there, and with the pages appearing, a glass field lies in the middle
    # of a section — and the check would catch the contents, passing that off
    # as a broken frame.
    pane_margin = column + tokens["space"]["between"] / 2
    pane = average(image, pane_margin, height * 0.5)

    # The panel is no longer a flat surface at all: a computed flow runs
    # under it (`4.0b-A06`). So the assertion changed its subject rather
    # than its tolerance — a tolerance wide enough to swallow the flow would
    # also swallow the difference between `FACE` and `FACE_LOW`, and the
    # check would stop being able to tell the panel from the column.
    #
    # What is asserted is that the colour on the panel is a colour the
    # flow's own ramp can produce. That catches the thing worth catching —
    # the shell painting something the tokens never named — and it says
    # nothing about which point of the ramp happened to be there, which is
    # a matter of the phase and not of correctness.
    calm = [hex_rgb(stop) for stop in nebula_ramp(finish_name, calm=True)]
    off = off_ramp(pane, calm)
    check("панель раздела — цвет из спокойной палитры течения", off <= 10,
          f"| {tuple(round(v) for v in pane)}, расходится на {off:.0f} "
          f"(не больше 10)")

    # And the areas are still separated. The system's means is a step of
    # value plus a hairline seam; under a flow the direction of the step is
    # no longer fixed — the flow can be darker or lighter than the column at
    # any moment — but the **discontinuity** at the boundary stays, and that
    # is what "separated" actually means.
    column_pixel = average(image, inside, height * 0.55)
    gap = abs(brightness(pane) - brightness(column_pixel))
    check("колонка и панель разделены — разрыв на границе", gap >= 4,
          f"| панель {brightness(pane):.0f}, колонка "
          f"{brightness(column_pixel):.0f}, разрыв {gap:.0f}")
    # The title bar lies over the vivid layer: the calm one covers only the
    # working area, and the bar is above it.
    bar_glass = glass_over(colors["FACE_LOW"], glass.get("bar", 1.0),
                           vivid_ramp)
    bar_at = at(width * 0.5, size["row"] / 2)
    check("полоса заголовка — FACE_LOW сквозь стекло",
          off_ramp(bar_at, bar_glass) <= 10,
          f"| {bar_at}, расходится на {off_ramp(bar_at, bar_glass):.0f}")

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
        # The open section is flush with the panel and the others stay
        # sunk. Under glass both are composites, so what is asserted is the
        # relation that carries the meaning: the open one is lighter than
        # its neighbours. That relation is what a person reads, and unlike
        # an exact colour it does not depend on where the flow happens to
        # be at the moment of the shot.
        other = middle + row if bottom + row < height * 0.7 else middle - row
        check("активный раздел заподлицо с панелью",
              brightness(at(inside, middle)) > brightness(at(inside, other)),
              f"| открытый {brightness(at(inside, middle)):.0f}, "
              f"соседний {brightness(at(inside, other)):.0f}")

        check("неактивный раздел остаётся утопленным",
              off_ramp(at(inside, other), column_glass) <= 10,
              f"| {at(inside, other)}")

    # The level strip along the bottom edge of the whole window: the
    # microphone belongs to the instrument as a whole, not to the current
    # section.
    strip = size["level_strip"]
    bottom = at(width * 0.5, height - 2)
    strip_glass = glass_over(colors["FACE_SUNK"], glass.get("strip", 1.0),
                             vivid_ramp)
    check("полоса уровня по нижней кромке — FACE_SUNK сквозь стекло",
          off_ramp(bottom, strip_glass) <= 10,
          f"| {bottom}, расходится на {off_ramp(bottom, strip_glass):.0f}")
    check("полоса уровня во всю ширину",
          off_ramp(at(4, height - 2), strip_glass) <= 10
          and off_ramp(at(width - 4, height - 2), strip_glass) <= 10,
          f"| слева {at(4, height - 2)}, справа {at(width - 4, height - 2)}")
    # Above the strip is the working area, and under glass "not the strip"
    # is no longer a matter of one colour: the strip and the panel are two
    # different sheets over one flow. What separates them is the step
    # between the sheets, and that is what is measured.
    above = at(width * 0.5, height - strip - 4)
    check("полоса не толще положенного",
          abs(brightness(above) - brightness(bottom)) >= 3,
          f"| над полосой {brightness(above):.0f}, "
          f"в полосе {brightness(bottom):.0f}")

    # There are no shadows: at the column's edge there must be no ramp to
    # dark. Under a living background the pixels there are no longer equal
    # to each other, so what is measured is the **shape** of the difference
    # rather than its absence: a shadow is dark against the seam and lifts
    # away from it, and a patch of light does not care where the seam is.
    #
    # Ten points across, the patch changes by a fraction of a value: its
    # own gradient is as wide as the window. Four are enough to tell the two
    # apart.
    edge = [average(image, column + d, height * 0.4) for d in (1, 3, 6, 10)]
    lift = brightness(edge[-1]) - brightness(edge[0])
    check("между колонкой и панелью нет тени", lift <= 2,
          f"| у шва {brightness(edge[0]):.1f}, поодаль "
          f"{brightness(edge[-1]):.1f}, подъём {lift:.1f} (не больше 2)")

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
