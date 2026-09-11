# -*- coding: utf-8 -*-
"""
Generating the shell's resources from tokens.json.

Plan item 4.0-F03; the decision is
[ADR 0005](../docs/adr/0005-control-library.md), where this is written down
as part of the decision itself rather than as a note under it.

There is no control library, so we write the styles ourselves, so the values
end up in XAML. Rewriting them by hand means keeping a second copy of the
palette, the spacing and the typography; it will part company with
`tokens.json` at the very first change, and in silence at that: a divergence
of two pixels is not visible, and a divergence in colour is not visible at
once and not to everyone.

So the XAML is generated. In exactly the same way as `Contract.g.cs` is
generated from the protocol's snapshot: one source, two sides.

What is generated is **values**, not styles. A style is a decision about how
a button looks; a person writes it and a person reads it. Here there are
only numbers and colours, which belong in one file.

Three files: a common one with the sizes and the typography, and one per
finish. The finishes are equal (`4.0-R08`), and dividing them into "the main
one" and "the inversion" would mean lying in the code's structure about what
is written in the design system.

To run:
    python tools/gen_xaml_tokens.py            write
    python tools/gen_xaml_tokens.py --check    compare without rewriting
"""

import json
import os
import sys

import nebula as nebula_mod

from console import use_utf8

use_utf8()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOKENS = os.path.join(ROOT, "docs", "design", "tokens.json")
OUT_DIR = os.path.join(ROOT, "shell", "Rina.Shell", "Generated")

HEADER = """<!--
    Порождено из docs/design/tokens.json.
    Не править руками: правьте токены и перезапустите
    python tools/gen_xaml_tokens.py

    Здесь только значения. Стили — решения о том, как выглядит контрол, —
    пишутся и читаются человеком и живут в Styles/.
-->
"""

DICT = ('<ResourceDictionary xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"\n'
        '                    xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"\n'
        '                    xmlns:sys="clr-namespace:System;assembly=System.Runtime">\n')


def key(name: str) -> str:
    """`FACE_HIGH` -> `FaceHigh`, `legend_column` -> `LegendColumn`."""
    return "".join(p.capitalize() for p in name.replace("-", "_").split("_"))


def finish_xaml(name: str, finish: dict, glass: dict) -> str:
    lines = [HEADER, f"<!-- Отделка «{finish['title']}» -->", DICT]
    for role, value in finish["color"].items():
        lines.append(f'  <Color x:Key="Color.{key(role)}">{value}</Color>')
        lines.append(f'  <SolidColorBrush x:Key="C.{key(role)}" '
                     f'Color="{value}" />')

    # Depth belongs to the finish, not to the geometry (4.0b-A06). The blur
    # and the offset are the same everywhere; what differs is what a shadow
    # is painted with — on a light panel it is a warm grey, on a dark one
    # something deeper than the panel itself.
    shadow = finish.get("shadow")
    if shadow:
        lines.append("")
        lines.append(f'  <Color x:Key="Color.Shadow">{shadow}</Color>')

    # The nebula: patches of light under the face, each drifting at a
    # period of its own (4.0b-A06). Colours only — the geometry and the
    # motion are shared and live in the common dictionary, and the drift
    # itself is the shell's, because it has to be able to stop.
    #
    # Every tint is a tint of **this** finish and of nothing else: the
    # category's cliché is a purple-to-blue glow, and the way not to
    # arrive at it is not to have a colour that the panel does not have.
    # Glass: the bars are the finish's own surface at less than full
    # strength, so the flow shows through them (`4.0b-A06`). A brush and not
    # an `Opacity` on the element: opacity applies to everything inside, and
    # the title, the buttons and the section names would fade with the
    # surface they stand on.
    #
    # The alpha comes first in `#aarrggbb` — a colour written with six
    # digits is opaque, and this is the one place where forgetting the pair
    # would silently give back exactly what we are trying to move away from.
    for part, surface in (("Bar", "FACE_LOW"), ("Column", "FACE_LOW"),
                          ("Strip", "FACE_SUNK"), ("Control", "FACE_HIGH"),
                          ("Raised", "FACE_HIGH"), ("Popup", "FACE_HIGH"),
                          ("Overlay", "FACE_HIGH"), ("Field", "GLASS")):
        share = glass.get(part.lower())
        if share is None:
            continue
        alpha = f"{round(share * 255):02x}"
        body = finish["color"][surface].lstrip("#")
        lines.append(f'  <SolidColorBrush x:Key="C.Glass.{part}" '
                     f'Color="#{alpha}{body}" />')

    # The light along the top edge of anything raised. One line, a pixel
    # thick, saying where the light falls from — the cheapest thing in the
    # system that reads as material rather than as paint.
    edge = glass.get("edge")
    if edge is not None:
        alpha = f"{round(edge * 255):02x}"
        body = finish["color"]["INK"].lstrip("#")
        lines.append(f'  <SolidColorBrush x:Key="C.Edge" '
                     f'Color="#{alpha}{body}" />')

    # The living background's palette, worked out here and handed over
    # ready (`4.0b-A06`). The shell computes none of it: the arithmetic
    # lives in `tools/nebula.py`, and the checks use that same module — a
    # formula implemented twice diverges at the first change to it, and
    # diverges quietly.
    #
    # A palette per accent, and two of each: vivid for the screen one looks
    # at, calm for the pages one reads on. Thirty per finish, and every one
    # of them checked against the ink and the legends.
    nebula = finish.get("nebula")
    if nebula:
        base = nebula["ramp"]
        face = finish["color"]["FACE"]
        lines.append("")
        lines.append(f'  <sys:Double x:Key="Nebula.Steps">'
                     f'{len(base)}</sys:Double>')
        lines.append(f'  <sys:Double x:Key="Nebula.Scale">'
                     f'{nebula["scale"]}</sys:Double>')
        lines.append(f'  <sys:Double x:Key="Nebula.Warp">'
                     f'{nebula["warp"]}</sys:Double>')
        for accent_name, accent in (finish.get("accents") or {}).items():
            vivid = nebula_mod.tinted(base, accent["signal"],
                                      nebula.get("accent", 0.0))
            calm = nebula_mod.dimmed(vivid, face, nebula.get("dim", 0.0))
            lines.append("")
            for at, stop in enumerate(vivid):
                lines.append(f'  <Color x:Key="Color.Nebula.'
                             f'{key(accent_name)}.{at}">{stop}</Color>')
            for at, stop in enumerate(calm):
                lines.append(f'  <Color x:Key="Color.Nebula.'
                             f'{key(accent_name)}.Calm.{at}">{stop}</Color>')

    lines.append("</ResourceDictionary>")
    return "\n".join(lines) + "\n"


def common_xaml(tokens: dict) -> str:
    space = tokens["space"]
    size = tokens["size"]
    radius = tokens["radius"]
    motion = tokens["motion"]
    typo = tokens["typography"]
    hatch = tokens["hatch"]

    lines = [HEADER, DICT]

    lines.append("  <!-- Пространство (§4 дизайн-системы) -->")
    for name, value in space.items():
        lines.append(f'  <sys:Double x:Key="Sp.{key(name)}">{value}</sys:Double>')
        lines.append(f'  <Thickness x:Key="Pad.{key(name)}">{value}</Thickness>')
        # A left-side thickness too, for a gap wanted on one side only:
        # the clear space around an irreversible action (SYSTEM §4) sits to
        # the left of a button in a list row, and the same space on its
        # right would push it off the edge. Writing the number into the
        # markup instead would mean a second copy of the value -- the copy
        # that quietly parts company with the scale when it next changes.
        lines.append(
            f'  <Thickness x:Key="Pad.{key(name)}Left">{value},0,0,0</Thickness>')

    lines.append("")
    lines.append("  <!-- Размеры -->")
    for name, value in size.items():
        lines.append(f'  <sys:Double x:Key="Size.{key(name)}">{value}</sys:Double>')
        # GridLength separately: a Double is not coerced in a column's
        # Width, and writing the number in the markup would mean keeping a
        # second copy of the value.
        lines.append(f'  <GridLength x:Key="Col.{key(name)}">{value}</GridLength>')

    lines.append("")
    lines.append("  <!-- Скругление: у приборов углы тугие, не больше 3 -->")
    for name, value in radius.items():
        lines.append(f'  <CornerRadius x:Key="Radius.{key(name)}">{value}</CornerRadius>')

    # The window's outer corner, and it is deliberately outside the ladder
    # above. The design system exempts it by name -- Windows draws it, and
    # it is not our value -- and for a window with transparency Windows
    # draws nothing, so the exemption has to be honoured by hand instead of
    # quietly becoming ours.
    window = tokens.get("window")
    if window and "corner" in window:
        lines.append('  <CornerRadius x:Key="Radius.Window">'
                     f'{window["corner"]}</CornerRadius>')

    # How densely a state's highlight is laid on. From the states table and
    # not from a number in the markup: it was opaque there, which made it a
    # repaint rather than a highlight -- the hatching of a dangerous button
    # vanished under the pointer, and the pointer is when it is read.
    lines.append("")
    lines.append("  <!-- Густота подсветки состояний (4.0b-E03) -->")
    for name, state in tokens["states"].items():
        if not isinstance(state, dict) or "wash" not in state:
            continue
        lines.append(f'  <sys:Double x:Key="State.{key(name)}.Wash">'
                     f'{state["wash"]}</sys:Double>')

    lines.append("")
    lines.append("  <!-- Гарнитуры -->")
    #: What to fall back on when the family is missing. Named per family
    #: rather than "ui or the other one": there are three now, and the old
    #: two-way split silently gave the display face a monospaced fallback.
    #:
    #: The fallbacks are real families, checked on the machine. The tokens
    #: used to name `Segoe UI Variable`, which Windows does not install
    #: under that name at all — it installs `... Display`, `... Text` and
    #: `... Small`. Every heading in the application had been set in the
    #: fallback, silently, since `4.0-R03`.
    FALLBACK = {
        # Bahnschrift is second on purpose: Century Gothic is not on every
        # Windows install, and falling straight through to a neutral
        # grotesque would lose the whole character of the setting exactly
        # where it is missing.
        "display": "Bahnschrift, Segoe UI Variable Display, Segoe UI, Arial",
        "ui": "Segoe UI Variable Text, Segoe UI, Arial",
        "mono": "Cascadia Mono, Consolas",
    }
    for name, value in typo["family"].items():
        fallback = FALLBACK.get(name, "Segoe UI, Arial")
        lines.append(f'  <FontFamily x:Key="Font.{key(name)}">{value}, '
                     f'{fallback}</FontFamily>')

    lines.append("")
    lines.append("  <!-- Роли текста (§3): семейство, размер, начертание -->")
    for role, spec in typo["role"].items():
        r = key(role)
        # The role's family, resolved here. The roles have named a family
        # since `4.0-R03`, and until `4.0b-A06` nothing read it: every style
        # inherited the one UI face, so `"family": "display"` was a word in
        # a file. A token nobody applies is not a decision but a note.
        lines.append(f'  <FontFamily x:Key="Type.{r}.Family">'
                     f'{{StaticResource Font.{key(spec.get("family", "ui"))}}}'
                     f'</FontFamily>')
        lines.append(f'  <sys:Double x:Key="Type.{r}.Size">{spec["size"]}</sys:Double>')
        lines.append(f'  <FontWeight x:Key="Type.{r}.Weight">{spec["weight"]}</FontWeight>')
        if "leading" in spec:
            lines.append(f'  <sys:Double x:Key="Type.{r}.Leading">'
                         f'{spec["leading"]}</sys:Double>')
        upper = "true" if spec.get("case") == "upper" else "false"
        lines.append(f'  <sys:Boolean x:Key="Type.{r}.Upper">{upper}</sys:Boolean>')

    lines.append("")
    lines.append("  <!-- Движение (§7): длительности в миллисекундах -->")
    for name, value in motion.items():
        # `easing` is curves and `background` is the backdrop's breathing:
        # both have their own place below. Here there are only durations,
        # and a dictionary among the numbers would mean a `Duration` made
        # out of a dictionary.
        if name in ("easing", "background"):
            continue
        lines.append(f'  <Duration x:Key="Motion.{key(name)}">'
                     f'0:0:{value / 1000:.3f}</Duration>')

    # The easings are a token too, not a number typed into every style. WPF
    # cannot do cubic-bezier, so the curves from the tokens are expressed by
    # the nearest standard ones: "appearance" is a deceleration towards the
    # end, "fade" an acceleration. The substitution is honest in meaning: the
    # first curve accelerates at the start, the second at the end.
    easing = motion.get("easing", {})
    if easing:
        lines.append("")
        lines.append(f'  <!-- Смягчение: {easing.get("default", "")} '
                     f'для появления, {easing.get("decay", "")} '
                     f'для затухания -->')
        lines.append('  <CubicEase x:Key="Ease.In" EasingMode="EaseOut" />')
        lines.append('  <CubicEase x:Key="Ease.Out" EasingMode="EaseIn" />')

    elevation = tokens.get("elevation")
    if elevation:
        lines.append("")
        lines.append("  <!-- Глубина (4.0b-A06): три уровня, дальше человек "
                     "не различает -->")
        for level, spec in elevation["level"].items():
            k = key(level)
            lines.append(f'  <sys:Double x:Key="Lift.{k}.Blur">'
                         f'{spec["blur"]}</sys:Double>')
            lines.append(f'  <sys:Double x:Key="Lift.{k}.Y">'
                         f'{spec["y"]}</sys:Double>')
            lines.append(f'  <sys:Double x:Key="Lift.{k}.Opacity">'
                         f'{spec["opacity"]}</sys:Double>')

    glass = tokens.get("glasswork")
    if glass:
        lines.append("")
        lines.append("  <!-- Стекло (4.0b-A06): сквозь полосы и органы "
                     "управления видно течение -->")
        for name, value in glass.items():
            if name == "note":
                continue
            lines.append(f'  <sys:Double x:Key="Glass.{key(name)}">'
                         f'{value}</sys:Double>')

    background = motion.get("background")
    if background:
        lines.append("")
        lines.append("  <!-- Дыхание фона (4.0b-A06). Когда фон замирает, "
                     "решает оболочка, а не эти числа -->")
        # From the tokens themselves, not from a list written out here:
        # the field's parameters changed once already, and a hand-written
        # tuple would have quietly stopped emitting the new one.
        for name, value in background.items():
            if name == "note":
                continue
            lines.append(f'  <sys:Double x:Key="Background.{key(name)}">'
                         f'{value}</sys:Double>')

    lines.append("")
    lines.append("  <!-- Штриховка опасного (§6): единственный признак необратимого -->")
    lines.append(f'  <sys:Double x:Key="Hatch.Angle">{hatch["angle"]}</sys:Double>')
    lines.append(f'  <sys:Double x:Key="Hatch.Line">{hatch["line"]}</sys:Double>')
    lines.append(f'  <sys:Double x:Key="Hatch.Gap">{hatch["gap"]}</sys:Double>')
    lines.append(f'  <sys:Double x:Key="Hatch.Opacity">{hatch["opacity"]}</sys:Double>')

    lines.append("</ResourceDictionary>")
    return "\n".join(lines) + "\n"


def accents_xaml(tokens) -> str:
    """
    The accent sets — as a resource dictionary per finish.

    Brushes rather than strings: the shell replaces `C.Signal` and
    `C.SignalSunk` whole, and keeping two representations of one colour
    beside each other would mean one day replacing one and forgetting the
    other.
    """
    lines = [HEADER, "<ResourceDictionary "
             'xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"',
             '                    '
             'xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"',
             '                    '
             'xmlns:sys="clr-namespace:System;assembly=System.Runtime">', ""]

    lines.append("  <!-- Имена акцентов: их показывает оболочка. -->")
    for name, title in (tokens.get("accent_titles") or {}).items():
        lines.append(f'  <sys:String x:Key="Accent.Title.{name}">{title}'
                     f"</sys:String>")
    lines.append("")
    lines.append('  <sys:String x:Key="Accent.Default">'
                 f'{tokens.get("default_accent", "amber")}</sys:String>')
    lines.append("")

    for finish, data in tokens["finishes"].items():
        lines.append(f"  <!-- {finish} -->")
        for name, accent in (data.get("accents") or {}).items():
            key = f"{finish}.{name}"
            lines.append(f'  <Color x:Key="Accent.{key}.Signal">'
                         f'{accent["signal"]}</Color>')
            lines.append(f'  <Color x:Key="Accent.{key}.SignalSunk">'
                         f'{accent["signal_sunk"]}</Color>')
        lines.append("")

    lines.append("</ResourceDictionary>")
    return "\n".join(lines) + "\n"


def files(tokens: dict) -> dict[str, str]:
    out = {"Tokens.g.xaml": common_xaml(tokens)}
    for name, finish in tokens["finishes"].items():
        out[f"Finish.{name.capitalize()}.g.xaml"] = finish_xaml(
            name, finish, tokens.get("glasswork") or {})
    if any(f.get("accents") for f in tokens["finishes"].values()):
        out["Accents.g.xaml"] = accents_xaml(tokens)
    return out


def main(argv) -> int:
    with open(TOKENS, encoding="utf-8") as f:
        tokens = json.load(f)
    wanted = files(tokens)

    if "--check" in argv:
        for name, text in wanted.items():
            path = os.path.join(OUT_DIR, name)
            if not os.path.isfile(path):
                print(f"нет порождённого файла: {name}")
                return 1
            with open(path, encoding="utf-8") as f:
                if f.read() != text:
                    print(f"{name} разошёлся с tokens.json")
                    print("Перезапустите: python tools/gen_xaml_tokens.py")
                    return 1
        print(f"ресурсы сходятся с tokens.json ({len(wanted)} файла)")
        return 0

    os.makedirs(OUT_DIR, exist_ok=True)
    for name, text in wanted.items():
        with open(os.path.join(OUT_DIR, name), "w", encoding="utf-8",
                  newline="\n") as f:
            f.write(text)
    print(f"порождено в {os.path.relpath(OUT_DIR, ROOT)}: "
          + ", ".join(sorted(wanted)))
    colors = len(next(iter(tokens["finishes"].values()))["color"])
    print(f"  цветов в отделке {colors}, ролей текста "
          f"{len(tokens['typography']['role'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
