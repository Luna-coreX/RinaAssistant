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
    print(f"=== F03: {os.path.basename(path)}, отделка «{finish_name}», "
          f"{width}x{height} ===")

    def at(x, y):
        return image.getpixel((int(x), int(y)))

    # Колонка разделов утоплена относительно панели: это ступень значения,
    # единственное средство возвышения в системе (теней нет).
    column = size["legend_column"]
    check("колонка разделов — FACE_LOW",
          near(at(column / 2, height * 0.55), colors["FACE_LOW"]),
          f"| {at(column / 2, height * 0.55)} против {colors['FACE_LOW']}")
    check("панель раздела — FACE",
          near(at(width * 0.7, height * 0.5), colors["FACE"]),
          f"| {at(width * 0.7, height * 0.5)} против {colors['FACE']}")
    check("полоса заголовка — FACE_LOW",
          near(at(width * 0.5, size["row"] / 2), colors["FACE_LOW"]),
          f"| {at(width * 0.5, size['row'] / 2)}")

    # Отметка активного раздела — единственный акцент в системе.
    row = size["row"]
    marker = at(1, row + row / 2)
    check("активный раздел отмечен акцентом",
          near(marker, colors["SIGNAL"], 6),
          f"| {marker} против {colors['SIGNAL']}")
    check("акцент шириной ровно 2 точки",
          near(at(1, row + row / 2), colors["SIGNAL"], 6)
          and not near(at(4, row + row / 2), colors["SIGNAL"], 6),
          f"| точка 4: {at(4, row + row / 2)}")

    # Активный раздел заподлицо с панелью, соседние — утоплены.
    check("активный раздел заподлицо с панелью",
          near(at(column / 2, row + row / 2), colors["FACE"]),
          f"| {at(column / 2, row + row / 2)}")
    check("неактивный раздел остаётся утопленным",
          near(at(column / 2, row * 3), colors["FACE_LOW"]),
          f"| {at(column / 2, row * 3)}")

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
