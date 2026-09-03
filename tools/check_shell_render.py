# -*- coding: utf-8 -*-
"""
Сверка нарисованного окна с токенами — по пикселям.

Задача плана 4.0-F03.

«Похоже на макет» — не проверка. Окно рисует WPF, стили пишет человек,
значения приходят из `tokens.json`, и разойтись они могут в любом из трёх
мест: опечатка в ключе ресурса, забытый `DynamicResource`, стиль, который
не применился. Ни одно из этих расхождений не заметно на глаз — цвет
«примерно тот» выглядит как цвет тот.

Поэтому оболочка умеет нарисовать себя в PNG (`--shot`), а здесь снимок
разбирается по точкам: колонка разделов, панель, отметка активного раздела,
полоса уровня, полоса заголовка. Ровно те места, где значение обязано
совпасть с токеном.

Проверяется **нарисованное**, а не разметка: разметку можно прочесть глазами,
и она всё равно ничего не говорит о том, что получилось на экране.

Запуск (снимки делает сама оболочка):
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
    """Совпадение с допуском: сглаживание краёв меняет точку на единицу."""
    return all(abs(x - y) <= tolerance for x, y in zip(a[:3], b))


def check_confirm(image, colors, tokens) -> int:
    """
    Окно подтверждения (4.0-F11): опасность штриховкой, а не цветом.

    Штриховка ищется по разбросу яркости в полосе кнопки: узор — это
    чередование, и на ровной заливке разброса не будет. Искать конкретную
    точку узора значило бы проверять, где именно легла линия, а не то, что
    узор есть.
    """
    width, height = image.size
    print(f"=== F11: окно подтверждения, {width}x{height} ===")

    check("окно на панели, а не на системном фоне",
          near(image.getpixel((width // 2, 8)), colors["FACE"]),
          f"| {image.getpixel((width // 2, 8))}")

    # Полоса, где стоит кнопка необратимого.
    row = int(height * 0.66)
    strip = [image.getpixel((x, row)) for x in range(24, 170)]
    greys = sorted({p[0] for p in strip})
    check("кнопка необратимого заштрихована",
          len(greys) >= 3 and max(greys) - min(greys) > 20,
          f"| оттенков {len(greys)}, размах {max(greys) - min(greys)}")

    # `getdata` объявлен к удалению в Pillow 14. Тот же случай, что и
    # `audioop` в ядре: узнать об этом при обновлении библиотеки — худший
    # момент, а `getcolors` делает ровно нужное и заодно считает точки.
    everything = {colour for _, colour in image.getcolors(1 << 24)}
    reds = [p for p in everything if p[0] > 150 and p[1] < 60 and p[2] < 60]
    check("красного нет нигде", not reds, f"| {reds[:3]}")

    check("акцент есть — это рамка фокуса на отказе",
          any(near(p, colors["SIGNAL"], 24) for p in everything))

    # Просвет вокруг необратимого — вдвое больше обычного (§4).
    gap = tokens["space"]["danger"]
    check("просвет вокруг необратимого объявлен вдвое большим",
          gap >= tokens["space"]["between"] * 2, f"| {gap}")

    # Верхняя граница выборки не должна задевать саму кнопку: она высотой в
    # орган управления, и половина её лежит выше середины строки.
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

    # Колонка разделов утоплена относительно панели: это ступень значения,
    # единственное средство возвышения в системе (теней нет).
    column = size["legend_column"]
    # Фон колонки меряется у правого края, а не посередине: посередине лежат
    # названия разделов, и точка попадает в букву. Сглаженная буква — это
    # ни фон, ни чернила, а что-то между, и проверка ловила бы её.
    inside = column - 8
    check("колонка разделов — FACE_LOW",
          near(at(inside, height * 0.55), colors["FACE_LOW"]),
          f"| {at(inside, height * 0.55)} против {colors['FACE_LOW']}")
    # Панель меряется в поле между колонкой и содержимым раздела, а не
    # посреди него: раньше там было пусто, а с появлением страниц посреди
    # раздела лежит стеклянное поле — и проверка ловила бы содержимое,
    # выдавая это за поломку каркаса.
    pane_margin = column + tokens["space"]["between"] / 2
    check("панель раздела — FACE",
          near(at(pane_margin, height * 0.5), colors["FACE"]),
          f"| {at(pane_margin, height * 0.5)} против {colors['FACE']}")
    check("полоса заголовка — FACE_LOW",
          near(at(width * 0.5, size["row"] / 2), colors["FACE_LOW"]),
          f"| {at(width * 0.5, size['row'] / 2)}")

    # Отметка активного раздела — единственный акцент в системе. Какой
    # раздел открыт, проверка не знает и знать не должна: она ищет отметку
    # сама. Привязка к первому разделу делала бы её проверкой снимка, а не
    # проверкой правила.
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

    # Полоса уровня вдоль нижней кромки всего окна: микрофон принадлежит
    # прибору целиком, а не текущему разделу.
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

    # Теней нет: над колонкой не должно быть градиента к тёмному.
    edge = [at(column + d, height * 0.4) for d in (1, 3, 6, 10)]
    check("между колонкой и панелью нет тени",
          all(near(p, colors["FACE"], 3) for p in edge), f"| {edge}")

    # --- F12: состояние связи видно и окрашено правильно -------------------
    # Проверяется по области подвала целиком, а не по отдельной точке: текст
    # сглажен, и попасть точкой в штрих буквы — это проверять удачу, а не цвет.
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

        # Красного в палитре нет вовсе: цвет опасности размывается от
        # повторения, и неполадка — не опасность.
        reds = [p for p in painted if p[0] > 150 and p[1] < 60 and p[2] < 60]
        check("красного в подвале нет", not reds, f"| {reds[:3]}")

    print()
    print("ИТОГО ошибок:", fails)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
