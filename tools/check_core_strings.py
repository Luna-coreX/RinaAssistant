# -*- coding: utf-8 -*-
"""
Everything the core says has an English translation.

The shell has had `check_strings.py` since `4.0-F08`: every word on the
screen goes through the table, and every key in the table is translated.
The core had nothing of the kind — it has `core/i18n.py` and the honest
fallback of returning the Russian original, which means a missing
translation is invisible. So half the step kinds in the command editor
came out in English and half in Russian on the same list, and nobody
found out until somebody looked at the screen.

A fallback that shows the original is right at run time and wrong at
build time: at run time it keeps the program working, at build time it
hides the gap. This is the build-time half.

To run:
    python tools/check_core_strings.py
"""
import io
import os
import re
import sys

from console import use_utf8

use_utf8()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

#: Not the core. `archive` is 3.1.0 kept for reference, `dist` and
#: `build` are made by the packager, `shell` is C# and has a check of its
#: own, and `venv` is somebody else's code entirely.
SKIP = {".git", "venv", "__pycache__", "archive", ".claude", "dist",
        "build", "shell", "node_modules", "tools"}

#: `tr` is what every module imports `core.i18n.t` as.
CALL = re.compile(r'\btr\(\s*(?:f)?["\']([^"\']*)["\']')
RUS = re.compile(r"[А-Яа-яЁё]")

def said(literal: str) -> str:
    """
    The string the program will actually hand to `tr`.

    What the source writes and what the program says are two things:
    a literal with a backslash and an `n` in it holds a newline. Compared
    unescaped, six plugin messages looked untranslated while their
    translations sat in the table under a key nobody would ever ask for.
    """
    out = literal.replace(chr(92) + chr(92), chr(0))
    for written, meant in ((chr(92) + "n", chr(10)),
                           (chr(92) + "t", chr(9)),
                           (chr(92) + "r", chr(13)),
                           (chr(92) + "'", "'"),
                           (chr(92) + chr(34), chr(34))):
        out = out.replace(written, meant)
    return out.replace(chr(0), chr(92))


fails = 0


def check(label, ok, detail=""):
    global fails
    if not ok:
        fails += 1
    print(("OK   " if ok else "FAIL "), label, detail)


def sources():
    for base, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP]
        for name in files:
            if name.endswith(".py"):
                yield os.path.join(base, name)


def main() -> int:
    from core.i18n import _EN, LANGUAGES

    print("=== ядро: сказанное переведено ===")

    asked, missing = set(), {}
    for path in sources():
        text = io.open(path, encoding="utf-8").read()
        for found in CALL.finditer(text):
            # What the source writes and what the program says are two
            # things: `tr("Ошибка:\n")` holds a newline, not a
            # backslash and an n. Compared unescaped, six plugin
            # messages looked untranslated while their translations sat
            # in the table under a key nobody would ever ask for.
            key = said(found.group(1))
            if not RUS.search(key):
                continue
            asked.add(key)
            if key in _EN:
                continue
            line = text[: found.start()].count("\n") + 1
            missing.setdefault(key, os.path.relpath(path, ROOT) + f":{line}")

    print(f"строк в коде: {len(asked)}, в таблице: {len(_EN)}")
    check("всё, что говорит ядро, переведено на английский",
          not missing, f"| без перевода: {len(missing)}")
    for key, where in list(missing.items())[:12]:
        print(f"        {where}: «{key}»")

    print(f"из них узнаны на месте: {len(asked)}")

    # --- and the tables translated through a variable -------------------
    #
    # `tr(title)` cannot be read off the page: the title comes out of a
    # list, and what is in the list is known only when it is imported.
    # These are exactly the places that put the mixed Russian-and-English
    # list of step kinds on the screen — half of them happened to be in
    # the table, half did not, and nothing said so.
    #
    # Named one by one rather than found by a rule. A rule that guessed
    # which lists are shown to a person would be wrong in both
    # directions, and the price of the list is one line when a new
    # table appears.
    from voice import hotkey_actions, system_control, user_commands

    tables = {
        "COMMAND_TYPES": [title for _v, title, _i
                          in user_commands.COMMAND_TYPES],
        "CONDITIONS": [title for _v, title in user_commands.CONDITIONS],
        "SYSTEM_ACTIONS": [title for _v, title
                           in user_commands.SYSTEM_ACTIONS],
        "DONE_MESSAGES": list(system_control.DONE_MESSAGES.values()),
        "CONFIRM_QUESTIONS": list(system_control.CONFIRM_QUESTIONS.values()),
        "HOTKEY_ACTIONS": [said for pair in hotkey_actions.HOTKEY_ACTIONS.values()
                           for said in pair[:2]],
    }

    lost = []
    counted = 0
    for name, titles in tables.items():
        for title in titles:
            if not RUS.search(str(title)):
                continue
            counted += 1
            if str(title) not in _EN:
                lost.append(f"{name}: «{title}»")
    check("и таблицы, которые переводятся на лету, тоже",
          not lost, f"| проверено {counted}, без перевода {len(lost)}")
    for one in lost[:12]:
        print(f"        {one}")

    # Every other language is allowed to be partial — that is stated in
    # `i18n_langs` and shown in the settings as a percentage — but
    # English is the second language of this program and is not.
    check("английский вообще есть", len(_EN) > 0 and "English" in LANGUAGES)

    print()
    print("ИТОГО ошибок:", fails)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
