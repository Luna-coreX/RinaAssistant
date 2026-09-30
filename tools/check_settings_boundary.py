# -*- coding: utf-8 -*-
"""
E06: the shell does not know the storage format, and names no key of its own.

Plan item 4.0-E06, the acceptance criterion; the decision is
[ADR 0006](../docs/adr/0006-settings-ownership.md). The core owns the
meaning of a value, the shell owns its appearance. That holds as long as the
shell asks — and it can stop holding in two ways, both silent.

**The shell learns where the data lies.** One `settings.json` in a path and
the boundary is gone: the shell reads the file, the core writes it, and they
part company on the first migration. Checked by the file names and by the
data directory's variables.

**A key outlives its meaning.** The shell names keys by hand — it has to, to
lay them out into sections and to write a hint. A key the core has dropped
leaves a row nobody can save, a hint nobody will see, or a branch that never
fires. Nothing says so: the row simply does not appear, and the code around
it goes on looking correct.

An obsolete key is the same case with a mark on it: the core keeps the data
but declares the key out of play, and the shell is obliged to stop naming
it.

To run:
    python tools/check_settings_boundary.py
"""
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
os.chdir(ROOT)

from console import use_utf8
use_utf8()

from core.settings_schema import CONSTRAINTS, SETTABLE

SHELL = os.path.join("shell", "Rina.Shell")
LAYOUT = os.path.join(SHELL, "Pages", "SettingsLayout.cs")

fails = 0


def check(label, cond, detail=""):
    global fails
    if not cond:
        fails += 1
    print(("OK   " if cond else "FAIL "), label, detail)


def shell_sources():
    """Every source of the shell, except what is generated or built."""
    for base, dirs, files in os.walk(SHELL):
        dirs[:] = [d for d in dirs if d not in ("obj", "bin", "Generated")]
        for name in files:
            if name.endswith((".cs", ".xaml")):
                yield os.path.join(base, name)


def read(path):
    return io.open(path, encoding="utf-8").read()


def code_only(text, xaml=False):
    """
    The same text without comments.

    Prose about code is not code — the lesson is already written down in
    `test_registry_only.py`, and this check walked into it at once: the
    explanation of why `config_version` is no longer asked for names
    `config_version`, and the check read that as the deed itself.

    A scanner rather than a regular expression, because a comment's mark
    lives inside string literals too: `"http://localhost:11434"` is an
    address, not a comment.
    """
    out, i, n = [], 0, len(text)
    while i < n:
        ch = text[i]
        if xaml and text.startswith("<!--", i):
            end = text.find("-->", i)
            i = n if end < 0 else end + 3
            continue
        if not xaml and text.startswith("//", i):
            end = text.find("\n", i)
            i = n if end < 0 else end
            continue
        if not xaml and text.startswith("/*", i):
            end = text.find("*/", i)
            i = n if end < 0 else end + 2
            continue
        if not xaml and text.startswith('@"', i):
            i += 2
            while i < n:
                if text[i] == '"' and text[i + 1:i + 2] == '"':
                    i += 2
                    continue
                if text[i] == '"':
                    i += 1
                    break
                out.append(text[i])
                i += 1
            continue
        if ch in "\"'":
            quote, i = ch, i + 1
            out.append(quote)
            while i < n and text[i] != quote:
                if text[i] == "\\":
                    out.append(text[i])
                    i += 1
                if i < n:
                    out.append(text[i])
                    i += 1
            # The closing quote goes out too: without it a literal stops
            # being a literal, and everything that looks for `"key"` finds
            # nothing. The first edition dropped it and reported "named 0" —
            # green, having checked nothing.
            if i < n:
                out.append(quote)
            i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


print("=== оболочка не знает, где лежат данные ===")

#: What the store's insides are called. A shell that names any of these is
#: reaching past the protocol — or is about to.
STORAGE_WORDS = ("settings.json", "commands.json", "plugins.json",
                 "history.json", "RinaAssistant/settings",
                 "config_version", "enabled_plugins", "custom_commands")

offenders = []
for path in shell_sources():
    text = code_only(read(path), xaml=path.endswith(".xaml"))
    for word in STORAGE_WORDS:
        if word in text:
            offenders.append(f"{os.path.relpath(path, SHELL)}: {word}")

check("оболочка не называет файлы хранилища", not offenders, f"| {offenders}")


print()
print("=== ключи оболочки существуют у ядра ===")

layout = code_only(read(LAYOUT))

#: Rows of the sections: `new("key", Word("…"), …)`.
IN_SECTION = re.compile(r'new\(\s*"([a-z_]+)"\s*,\s*Word\(')
#: Arms of `HintInField` and `ClearWordOf`: `"key" => …`.
IN_SWITCH = re.compile(r'^\s*"([a-z_]+)"\s*=>', re.MULTILINE)
#: Contents of the `Elsewhere` and `ShellKnows` sets.
IN_SET = re.compile(r'HashSet<string>\s+(\w+)\s*=\s*\[(.*?)\];', re.S)

named = {}


def remember(key, where):
    named.setdefault(key, set()).add(where)


for key in IN_SECTION.findall(layout):
    remember(key, "раскладка")
for key in IN_SWITCH.findall(layout):
    remember(key, "подсказка")
for name, body in IN_SET.findall(layout):
    for key in re.findall(r'"([a-z_]+)"', body):
        remember(key, name)

#: A branch on a particular key anywhere in the shell: `key == "…"`,
#: `key is "…" or "…"`. Such a branch is behaviour attached to a name, and
#: it rots exactly like a row in the layout.
BRANCH = re.compile(r'\bkey\s+(?:==|is)\s+("(?:[a-z_]+)"(?:\s+or\s+"[a-z_]+")*)')
for path in shell_sources():
    for group in BRANCH.findall(code_only(read(path),
                                          xaml=path.endswith(".xaml"))):
        for key in re.findall(r'"([a-z_]+)"', group):
            remember(key, os.path.basename(path))

known = set(SETTABLE)
unknown = sorted(k for k in named if k not in known)
check(f"каждый названный ключ есть в схеме ядра (названо {len(named)})",
      not unknown,
      "| " + ", ".join(f"{k} ({', '.join(sorted(named[k]))})" for k in unknown))


print()
print("=== устаревшие ключи оболочка не называет ===")

# The core keeps the data but declares the key out of play; the shell naming
# it is a row, a hint or a branch that will never fire.
obsolete = sorted(k for k in named
                  if CONSTRAINTS.get(k) and CONSTRAINTS[k].obsolete)
check("устаревшее не разложено и не подсказано", not obsolete,
      "| " + ", ".join(f"{k} ({', '.join(sorted(named[k]))})" for k in obsolete))


print()
print("ИТОГО ошибок:", fails)
sys.exit(1 if fails else 0)
