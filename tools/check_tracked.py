# -*- coding: utf-8 -*-
"""
What the program is built from is in the repository.

**A fresh clone did not build.** `.gitignore` carries the Python
template's `*.manifest`, written for PyInstaller, which this project does
not use; it quietly took `shell/Rina.Shell/app.manifest` — the file that
declares per-monitor DPI awareness and that the project names in
`<ApplicationManifest>`. On the developer's disk the file was there and
everything built; from the repository, `dotnet build` stopped at CS1926.
The same template had already hidden `/site` once, and that was closed
for the site alone. This closes the class: a file inside the folders the
program is made of, which git ignores, is a failure — whichever rule it
was that caught it.

Build output and interpreter caches are not sources and are left alone.
`docs/` is left alone on purpose: notes a person keeps out of the
repository are theirs to keep.

To run:
    python tools/check_tracked.py
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

from console import use_utf8  # noqa: E402

use_utf8()

#: What the program is made of.
SOURCES = ["shell", "core", "voice", "plugins", "tools", "rina_core.py",
           "requirements.txt"]

#: What is built or cached there, and is right to be ignored.
PRODUCED = {"bin", "obj", "__pycache__"}

fails = 0


def check(label, cond, detail=""):
    global fails
    if not cond:
        fails += 1
    print(("OK   " if cond else "FAIL "), label, detail)


def ignored_sources():
    """Paths git ignores inside the sources, less what is produced there."""
    listed = subprocess.run(
        ["git", "ls-files", "--others", "--ignored", "--exclude-standard",
         "--directory", "--", *SOURCES],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
        timeout=60)
    if listed.returncode != 0:
        raise OSError(listed.stderr.strip() or "git ls-files failed")
    found = []
    for path in listed.stdout.splitlines():
        parts = path.strip().strip("/").split("/")
        if not parts or PRODUCED & set(parts) or path.endswith(".pyc"):
            continue
        found.append(path.strip())
    return found


print("=== исходники лежат в хранилище ===")
try:
    hidden = ignored_sources()
    check("ни один исходник не спрятан .gitignore", not hidden,
          f"| спрятаны: {hidden} — свежий клон их не получит")
except (OSError, subprocess.TimeoutExpired) as trouble:
    check("git ответил, что он прячет", False, f"| {trouble}")

# The one that was lost, asked by name as well: it is what a build of the
# shell cannot do without, and a check that only listed would say nothing
# if git stopped listing ignored files for some other reason.
try:
    named = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "shell/Rina.Shell/app.manifest"],
        cwd=ROOT, capture_output=True, text=True, timeout=30)
    check("манифест оболочки в хранилище", named.returncode == 0,
          "| без него свежий клон не собирается: CS1926")
except (OSError, subprocess.TimeoutExpired) as trouble:
    check("git ответил про манифест", False, f"| {trouble}")

print()
print("ИТОГО ошибок:", fails)
sys.exit(1 if fails else 0)
