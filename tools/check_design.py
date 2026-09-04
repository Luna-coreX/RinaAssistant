# -*- coding: utf-8 -*-
"""
Сверка дизайна с инвентарём поверхности и с направлением.

Задача плана 4.0-R11. У интерфейса нет аналога golden-набора: после редизайна
всё отличается намеренно, и автоматически отличить «так задумано» от
«потеряли» нечем. Роль критерия играет эта сверка.

Проверяется двумя способами:

    1. Каждое действие из раздела «Доступно только отсюда» инвентаря
       поверхности имеет адрес в новой информационной архитектуре.
       Потерянная кнопка — потерянная возможность, и ядро об этом
       не узнает: golden-набор проверяет ядро, а не окно.

    2. Токены и макет отвечают «нет» на двенадцать вопросов направления.
       Система построена так, чтобы честное следование ей давало это
       автоматически; проверка ловит отступления.

Запуск:
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
# 1. Каждое действие имеет адрес
# ---------------------------------------------------------------------------
def only_here_actions():
    """Строки таблицы «Доступно только отсюда» из инвентаря поверхности."""
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


#: Куда переехал каждый экран 3.1.0. Ключ — как раздел назывался в инвентаре.
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
    # Адрес бывает составным: «Настройки → Голос» и «Настройки, Рина».
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

# радиус
check("радиус не больше 3",
      max(tokens["radius"].values()) <= 3, f"| {tokens['radius']}")

# ...и не только в токенах. Первая редакция смотрела сюда и была зелёной,
# пока в разметке стоял тумблер радиусом 11: правило сторожили в
# источнике, а нарушали у потребителя.
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

# один акцент
for key, finish in tokens["finishes"].items():
    colors = finish["color"]
    accents = [k for k in colors if k.startswith("SIGNAL")]
    check(f"[{key}] акцент один (плюс его нажатое состояние)",
          set(accents) == {"SIGNAL", "SIGNAL_SUNK"}, f"| {accents}")

# красного нет
def is_reddish(hex_color):
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return r > 150 and g < 60 and b < 60

for key, finish in tokens["finishes"].items():
    reds = [k for k, v in finish["color"].items() if is_reddish(v)]
    check(f"[{key}] красного в палитре нет", not reds, f"| {reds}")

# опасность — штриховкой
check("опасность обозначена штриховкой",
      tokens["states"]["danger"].get("hatch") is True
      and "hatch" in tokens)
check("у ошибки и опасности разные средства",
      tokens["states"]["error"].get("hatch") is not True)

# тени и размытия нет
check("в токенах нет теней и размытий",
      not any(k in tokens for k in ("shadow", "blur", "elevation")))
if mockups:
    bad = [w for w in ("box-shadow", "text-shadow", "filter: blur", "backdrop-filter")
           if w in mockups]
    check("в макете нет теней и размытий", not bad, f"| {bad}")

# градиент ровно один — полоса уровня
if mockups:
    gradients = re.findall(r"linear-gradient", mockups)
    # repeating-linear-gradient штриховки считается отдельно
    plain = len(gradients) - mockups.count("repeating-linear-gradient")
    check("градиент ровно один (полоса уровня)", plain == 1, f"| {plain}")

# табличные цифры
check("цифры моноширинные",
      tokens["typography"]["role"]["figure"]["family"] == "mono"
      and tokens["typography"]["role"]["figure"].get("tabular") is True)

# послесвечение
check("состояние гаснет, а не переключается",
      tokens["motion"]["afterglow"] >= 500,
      f"| {tokens['motion']['afterglow']} мс")

# --- движение объявлено и **применено** -------------------------------------
#
# Токен, которым никто не пользуется, — это намерение, а не решение.
# Система движения (SYSTEM §7) была порождена в `Motion.*` и не
# использовалась нигде: состояния переключались мгновенно, а полоса уровня
# скакала между нулём и сорока процентами. Двенадцать вопросов направления
# называют это прямым «не в стиле», и проверка на токены его не поймала —
# значение-то в файле было.
SHELL = os.path.join(ROOT, "shell", "Rina.Shell")
used = []
for base, dirs, files in os.walk(SHELL):
    dirs[:] = [d for d in dirs if d not in ("obj", "bin", "Generated")]
    for name in files:
        if name.endswith((".xaml", ".cs")):
            used.append(read(os.path.join(base, name)))
code = chr(10).join(used)

for name in ("Press", "State", "Panel", "Afterglow"):
    applied = f"Motion.{name}" in code
    check(f"длительность {name} применена, а не только объявлена", applied,
          "" if applied else "| токен без применения — намерение, а не решение")

on_strip = "Motion.Afterglow" in read(os.path.join(SHELL, "MainWindow.xaml.cs"))
check("послесвечение висит на полосе уровня", on_strip,
      "" if on_strip else "| «полоса не переключается между выключено и "
                          "включено» (DIRECTION §4)")

# просвет вокруг опасного вдвое больше обычного
check("опасное отделено пустотой",
      tokens["space"]["danger"] >= tokens["space"]["between"] * 2,
      f"| {tokens['space']['danger']} против {tokens['space']['between']}")

print()
print("=== R08: две отделки равноправны ===")
silver = set(tokens["finishes"]["silver"]["color"])
black = set(tokens["finishes"]["black"]["color"])
check("набор ролей совпадает", silver == black,
      f"| только в одной: {silver ^ black}")
check("стекло в обеих отделках тёмное",
      tokens["finishes"]["silver"]["color"]["GLASS"].lower() < "#404040"
      and tokens["finishes"]["black"]["color"]["GLASS"].lower() < "#404040")

print()
print("ИТОГО ошибок:", fails)
sys.exit(1 if fails else 0)
