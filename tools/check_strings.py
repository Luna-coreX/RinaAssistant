# -*- coding: utf-8 -*-
"""
F08: ни одна строка интерфейса не осталась мимо перевода.

Правило с зубами. Решение «слова интерфейса живут в оболочке» держится
ровно до первой строки, написанной литералом: она молча останется русской
на любом языке, и заметит это только тот, кто переключил язык и посмотрел
глазами на все пять разделов.

Проверяется три вещи:

* каждый показанный человеку литерал идёт через `S(...)` или `{loc:S ...}`;
* каждый использованный ключ есть в `interface.json`;
* в таблице нет ключей, которых нет в коде, — иначе переводчик тратит
  время на строки, которые никто не покажет.

Запуск:
    python tools/check_strings.py
"""
import io
import json
import os
import re
import sys

from console import use_utf8

use_utf8()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHELL = os.path.join(ROOT, "shell", "Rina.Shell")
TABLE = os.path.join(SHELL, "Strings", "interface.json")

# Startup.cs — подписи самопроверок: они идут в консоль разработчику, а не
# человеку, и переводить их значило бы переводить свои же логи.
SKIP_FILES = {"Startup.cs", "Loc.cs"}

#: `Platform` — системный слой: он разговаривает с Windows и с ядром, а не
#: с человеком. Русские строки там — это имена системных папок
#: («Загрузки»), слова-фильтры мусорных ярлыков («удалить», «справка») и
#: причины отказа, уходящие ядру. Переводить их значило бы искать папку
#: «Downloads» под английским языком интерфейса.
SKIP_DIRS = {"obj", "bin", "Generated", "Platform"}

#: Пометка «это не слово интерфейса»: строка не показывается человеку.
#: Пометка стоит на самой строке, а не в списке исключений где-то ещё:
#: список пришлось бы держать в согласии с кодом руками, а он расходится
#: молча — ровно та беда, ради которой затевалась вся проверка.
NOT_UI = "// не интерфейс"

RUS = re.compile(r"[А-Яа-яЁё]")
#: `S(...)` переводит здесь, `Word(...)` помечает строку для перевода
#: в другом месте — обе формы одинаково законны и обе дают ключ.
CALL = re.compile(r'\b(?:S|Word)\(\s*@?"([^"]*)"')
#: `S("часть" + "часть")` — фраза, собранная из двух переводов.
GLUE = re.compile(r'(?:S|Word)\(\s*@?"[^"]*"\s*\+')
XAML_CALL = re.compile(r"\{loc:S '([^']*)'\}")
CS_LITERAL = re.compile(r'"([^"\n]*[А-Яа-яЁё][^"\n]*)"')
XAML_ATTR = re.compile(r'\b(?:Text|Content|ToolTip|Title)="([^"{}]*[А-Яа-яЁё][^"{}]*)"')

fails = 0


def check(label, ok, detail=""):
    global fails
    if not ok:
        fails += 1
    print(("OK   " if ok else "FAIL "), label, detail)


def sources():
    for base, dirs, files in os.walk(SHELL):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in files:
            if name in SKIP_FILES:
                continue
            if name.endswith(".cs") and not name.endswith(".g.cs"):
                yield os.path.join(base, name), "cs"
            elif name.endswith(".xaml"):
                yield os.path.join(base, name), "xaml"


def main() -> int:
    with io.open(TABLE, encoding="utf-8") as source:
        table = json.load(source)

    used = set()
    loose = []

    for path, kind in sources():
        text = io.open(path, encoding="utf-8").read()
        short = os.path.relpath(path, ROOT)

        if kind == "xaml":
            used.update(XAML_CALL.findall(text))
            for body in XAML_ATTR.findall(text):
                loose.append((short, body))
            continue

        for number, line in enumerate(text.split("\n"), 1):
            stripped = line.lstrip()
            if stripped.startswith(("//", "///", "*")):
                continue

            # Вызовы собираются **до** отсева по кириллице: переводимая
            # строка бывает и без русских букв — адрес, время, имя. Такая
            # раньше не попадала в «использованные» и выглядела лишней в
            # таблице, хотя стояла в коде.
            used.update(CALL.findall(line))
            if not RUS.search(line):
                continue
            if NOT_UI in line:
                continue

            # Строка в порядке, если она есть в таблице: значит, её где-то
            # переводят. Так проходят и ключи, отданные в `S` не соседним
            # символом — тернарный выбор, список разделов, — и не проходит
            # новый литерал, которого в таблице нет: его-то и забыли.
            for body in CS_LITERAL.findall(line):
                if body not in table:
                    loose.append((f"{short}:{number}", body))

    # Склеенная строка переводится по кускам: в таблице оказываются
    # обрывки, а человек видит фразу, собранную из двух переводов. Ловим
    # это прямо, а не по следам в таблице.
    glued = []
    for path, kind in sources():
        if kind == 'xaml':
            continue
        text = io.open(path, encoding='utf-8').read()
        short = os.path.relpath(path, ROOT)
        for found in GLUE.finditer(text):
            line = text[:found.start()].count(chr(10)) + 1
            glued.append(f'{short}:{line}')
    check('строка интерфейса не склеена из кусков', not glued, f'| {glued}')

    print(f"строк в таблице: {len(table)}, использовано в коде: {len(used)}")

    check("все показанные строки идут через перевод", not loose,
          f"| мимо перевода: {len(loose)}")
    for where, body in loose[:12]:
        print(f"        {where}: «{body}»")

    unknown = sorted(used - set(table))
    check("каждый ключ есть в таблице", not unknown, f"| {unknown[:5]}")

    stale = sorted(set(table) - used)
    check("в таблице нет строк, которых нет в коде", not stale,
          f"| лишних {len(stale)}")
    for key in stale[:8]:
        print(f"        «{key}»")

    english = sum(1 for row in table.values() if "English" in row)
    check("английский переведён целиком", english == len(table),
          f"| {english} из {len(table)}")

    print()
    print("ИТОГО ошибок:", fails)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
