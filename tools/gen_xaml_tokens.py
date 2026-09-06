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


def finish_xaml(name: str, finish: dict) -> str:
    lines = [HEADER, f"<!-- Отделка «{finish['title']}» -->", DICT]
    for role, value in finish["color"].items():
        lines.append(f'  <Color x:Key="Color.{key(role)}">{value}</Color>')
        lines.append(f'  <SolidColorBrush x:Key="C.{key(role)}" '
                     f'Color="{value}" />')
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

    lines.append("")
    lines.append("  <!-- Гарнитуры -->")
    for name, value in typo["family"].items():
        fallback = ("Segoe UI, Segoe UI Variable" if name == "ui"
                    else "Cascadia Mono, Consolas")
        lines.append(f'  <FontFamily x:Key="Font.{key(name)}">{value}, '
                     f'{fallback}</FontFamily>')

    lines.append("")
    lines.append("  <!-- Роли текста (§3): размер, начертание, трекинг -->")
    for role, spec in typo["role"].items():
        r = key(role)
        lines.append(f'  <sys:Double x:Key="Type.{r}.Size">{spec["size"]}</sys:Double>')
        lines.append(f'  <FontWeight x:Key="Type.{r}.Weight">{spec["weight"]}</FontWeight>')
        tracking = spec.get("tracking", 0)
        # In WPF, tracking is set in em units through Typography/RenderOptions
        # rather than directly; here we give out the fraction, and a style applies it.
        lines.append(f'  <sys:Double x:Key="Type.{r}.Tracking">{tracking}</sys:Double>')
        if "leading" in spec:
            lines.append(f'  <sys:Double x:Key="Type.{r}.Leading">'
                         f'{spec["leading"]}</sys:Double>')
        upper = "true" if spec.get("case") == "upper" else "false"
        lines.append(f'  <sys:Boolean x:Key="Type.{r}.Upper">{upper}</sys:Boolean>')

    lines.append("")
    lines.append("  <!-- Движение (§7): длительности в миллисекундах -->")
    for name, value in motion.items():
        if name == "easing":
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
        out[f"Finish.{name.capitalize()}.g.xaml"] = finish_xaml(name, finish)
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
