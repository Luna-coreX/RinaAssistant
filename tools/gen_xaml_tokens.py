# -*- coding: utf-8 -*-
"""
Порождение ресурсов оболочки из tokens.json.

Задача плана 4.0-F03; решение — [ADR 0005](../docs/adr/0005-control-library.md),
где это записано как часть самого решения, а не как примечание под ним.

Библиотеки контролов нет, значит стили пишем сами, значит значения окажутся
в XAML. Переписать их руками — завести вторую копию палитры, отступов и
типографики; она разойдётся с `tokens.json` на первой же правке, причём
молча: расхождение в два пикселя не видно, а расхождение в цвет видно не
сразу и не всем.

Поэтому XAML порождается. Ровно так же, как `Contract.g.cs` порождается из
снимка протокола: один источник, две стороны.

Порождаются **значения**, а не стили. Стиль — это решение о том, как
выглядит кнопка; его пишет человек и читает человек. Здесь только числа и
цвета, которым место в одном файле.

Три файла: общий с размерами и типографикой и по одному на отделку. Отделки
равноправны (`4.0-R08`), и делить их на «основную» и «инверсию» значило бы
соврать в устройстве кода о том, что записано в дизайн-системе.

Запуск:
    python tools/gen_xaml_tokens.py            записать
    python tools/gen_xaml_tokens.py --check    сверить, не переписывая
"""

import json
import os
import sys

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
        # GridLength отдельно: в Width колонки Double не приводится, а
        # писать число в разметке значило бы завести вторую копию значения.
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
        # В WPF трекинг задаётся в единицах em через Typography/RenderOptions
        # не напрямую; здесь отдаём долю, а применяет её стиль.
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

    lines.append("")
    lines.append("  <!-- Штриховка опасного (§6): единственный признак необратимого -->")
    lines.append(f'  <sys:Double x:Key="Hatch.Angle">{hatch["angle"]}</sys:Double>')
    lines.append(f'  <sys:Double x:Key="Hatch.Line">{hatch["line"]}</sys:Double>')
    lines.append(f'  <sys:Double x:Key="Hatch.Gap">{hatch["gap"]}</sys:Double>')
    lines.append(f'  <sys:Double x:Key="Hatch.Opacity">{hatch["opacity"]}</sys:Double>')

    lines.append("</ResourceDictionary>")
    return "\n".join(lines) + "\n"


def files(tokens: dict) -> dict[str, str]:
    out = {"Tokens.g.xaml": common_xaml(tokens)}
    for name, finish in tokens["finishes"].items():
        out[f"Finish.{name.capitalize()}.g.xaml"] = finish_xaml(name, finish)
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
