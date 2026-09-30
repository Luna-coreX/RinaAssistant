# -*- coding: utf-8 -*-
"""
String literals that were mangled on their way into the file.

A narrow check about one recurring accident: a Windows path written through
a generating script, where `\\n` in `...System32\\notepad.exe` became a real
newline and the literal turned into two lines with the `n` eaten. The program
then quietly looks for `otepad.exe`.

It has happened four times in one sitting, and once in a different shape: a
`\\b` in a regular expression became a backspace character, U+0008, sitting
inside `core/router.py` and making "почему ты…" fall through to a web search.
Both are invisible when reading and both survive review, because what is on
the screen is exactly what was meant — the file just does not contain it.

**Two things are looked for.**

*Control characters* anywhere in a source file, other than tab and newline.
There is no honest reason for one; every occurrence so far has been an escape
that got eaten.

*Verbatim C# strings that span lines.* `@"..."` across a line break is legal
and, in this codebase, has always been the same accident: a path whose
backslash-escape was interpreted one layer too early. A real multi-line
literal here would be written as a raw string or built up in code.
"""
import io
import os
import re
import sys

ROOT = r"C:\DevStation\PCDev\DesktopApps\RinaAssistant"
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

from console import use_utf8

use_utf8()

#: Where source lives. The generated files are included on purpose: a
#: generator that mangles a literal is exactly the case this exists for.
LOOK_IN = ("core", "voice", "plugins", "tools", "shell/Rina.Shell",
           "shell/Rina.Protocol")
SUFFIXES = (".py", ".cs", ".xaml")
SKIP_DIRS = {"__pycache__", "bin", "obj", ".git", "venv"}

#: Tab and newline are ordinary; a carriage return is ordinary on Windows.
ALLOWED = {"\t", "\n", "\r"}

#: A verbatim C# string, from `@"` to the closing quote, allowed to contain
#: doubled quotes. Across lines is what we are looking for.
VERBATIM = re.compile(r'@"(?:[^"]|"")*"', re.DOTALL)

fails = 0


def check(label, cond, detail=""):
    global fails
    if not cond:
        fails += 1
    print(("OK   " if cond else "FAIL "), label, detail)


def sources():
    for where in LOOK_IN:
        for root, dirs, names in os.walk(os.path.join(ROOT, where)):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for name in names:
                if name.endswith(SUFFIXES):
                    yield os.path.join(root, name)


print("=== литералы не покалечены при записи ===")

controls, split = [], []
for path in sources():
    try:
        text = io.open(path, encoding="utf-8").read()
    except (UnicodeDecodeError, OSError):
        continue
    rel = os.path.relpath(path, ROOT)

    for at, line in enumerate(text.split("\n"), 1):
        for ch in line:
            if ch < " " and ch not in ALLOWED:
                controls.append(f"{rel}:{at}: U+{ord(ch):04X}")
                break

    if path.endswith(".cs"):
        for found in VERBATIM.finditer(text):
            if "\n" in found.group(0):
                at = text[:found.start()].count("\n") + 1
                shown = found.group(0)[:50].replace("\n", "\\n")
                split.append(f"{rel}:{at}: {shown}")

check("управляющих символов в исходниках нет", controls == [],
      "| " + "; ".join(controls[:5]) if controls else "")
check("дословных строк, разорванных переносом, нет", split == [],
      "| " + "; ".join(split[:5]) if split else "")

print()
print("ИТОГО ошибок:", fails)
sys.exit(1 if fails else 0)
