# -*- coding: utf-8 -*-
"""
F08: not one interface string was left out of translation.

A rule with teeth. The decision "the words of the interface live in the
shell" holds exactly until the first string written as a literal: it will
silently stay Russian in any language, and the only person to notice will be
whoever switched the language and looked at all five sections with their own
eyes.

Three things are checked:

* every literal shown to a person goes through `S(...)` or `{loc:S ...}`;
* every key used is in `interface.json`;
* the table holds no keys that are absent from the code — otherwise a
  translator spends time on strings nobody will show.

To run:
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

# Startup.cs — the self-checks' captions: they go to a developer's console
# rather than to a person, and translating them would mean translating our
# own logs.
SKIP_FILES = {"Startup.cs", "Loc.cs"}

#: `Platform` is the system layer: it talks to Windows and to the core, not
#: to a person. The Russian strings there are the names of system folders
#: ("Загрузки"), filter words for junk shortcuts ("удалить", "справка") and
#: refusal reasons going to the core. Translating them would mean looking for
#: a "Downloads" folder under an English interface language.
SKIP_DIRS = {"obj", "bin", "Generated", "Platform"}

#: The mark "this is not an interface word": the string is not shown to a
#: person. The mark stands on the string itself rather than in a list of
#: exceptions somewhere else: a list would have to be kept in agreement with
#: the code by hand, and it drifts in silence — precisely the trouble this
#: whole check was started for.
NOT_UI = "// not UI"

RUS = re.compile(r"[А-Яа-яЁё]")
#: `S(...)` translates here, `Word(...)` marks a string for translation
#: elsewhere — both forms are equally lawful and both give a key.
CALL = re.compile(r'\b(?:S|Word)\(\s*@?"([^"]*)"')
#: `S("часть" + "часть")` — a phrase assembled from two translations.
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

            # The calls are collected **before** the Cyrillic filter: a
            # translatable string sometimes has no Russian letters — an
            # address, a time, a name. Such a one used not to get into "the
            # used" and looked superfluous in the table, although it stood
            # in the code.
            used.update(CALL.findall(line))
            if not RUS.search(line):
                continue
            if NOT_UI in line:
                continue

            # A string is in order if it is in the table: that means it is
            # translated somewhere. That way through go the keys handed to
            # `S` by something other than the neighbouring symbol — a
            # ternary choice, a list of sections — and through does not go a
            # new literal that is not in the table: that is the forgotten
            # one.
            for body in CS_LITERAL.findall(line):
                if body not in table:
                    loose.append((f"{short}:{number}", body))

    # A glued string is translated in pieces: the table ends up with
    # fragments, while a person sees a phrase assembled from two
    # translations. We catch that directly rather than by its traces in the
    # table.
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
