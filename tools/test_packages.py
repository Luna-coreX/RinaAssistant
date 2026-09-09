# -*- coding: utf-8 -*-
"""
T-20 / 4.0b-A15: only what the code names gets installed.

Installing a package downloads and **runs** somebody else's code. The one
thing standing between "install this for me" and "run this on my machine"
is the rule that the name comes from `PACKAGES` and not from a message.
That rule is what is checked here.

Nothing is installed: what is checked is **what would have been run**. A
real `pip` here would mean minutes, a network and a changed environment —
all to answer a question that is visible in the command's arguments.
"""
import os
import sys

sys.path.insert(0, r"C:\DevStation\PCDev\DesktopApps\RinaAssistant")
sys.path.insert(0, os.path.join(
    r"C:\DevStation\PCDev\DesktopApps\RinaAssistant", "tools"))

from console import use_utf8
from core import models

use_utf8()

fails = 0


def check(label, cond, detail=""):
    global fails
    if not cond:
        fails += 1
    print(("OK   " if cond else "FAIL "), label, detail)


print("=== список закрыт ===")
check("пакеты перечислены в коде", len(models.PACKAGES) > 0,
      f"| {len(models.PACKAGES)}")
check("у каждого есть имя для pip и имя для импорта",
      all(p.pip and p.module for p in models.PACKAGES))
check("незнакомого в списке нет", models.find_package("evil-package") is None)


# --- what would actually be run ------------------------------------------
launched = []


class Caught(Exception):
    pass


def catch(command, **_kw):
    launched.append(list(command))
    raise Caught()


print()
print("=== запускается только названное ===")
import subprocess                                       # noqa: E402

real_popen = subprocess.Popen
subprocess.Popen = catch
try:
    known = models.find_package("pkg-vosk")
    install = models.Install(known)
    install._run()
finally:
    subprocess.Popen = real_popen

check("pip был вызван", len(launched) == 1, f"| {launched}")
if launched:
    command = launched[0]
    check("своим интерпретатором, а не системным",
          command[0] == sys.executable, f"| {command[0]}")
    check("именно pip install", command[1:4] == ["-m", "pip", "install"],
          f"| {command[1:4]}")
    # The whole point of the closed list, in one assertion: what reaches the
    # command line is the name written in `PACKAGES`.
    check("и ставится имя из списка", command[-1] == known.pip,
          f"| {command[-1]!r} против {known.pip!r}")
    check("ничего лишнего в команде не приехало",
          all(not arg.startswith("http") and ";" not in arg
              and "&" not in arg for arg in command),
          f"| {command}")

print()
print("=== имя из сообщения не проходит ===")
# What the shell sends is an identifier, and it is looked up. A payload
# naming a package directly must find nothing — this is the line that keeps
# a protocol message from becoming an install.
for made_up in ("requests", "vosk", "../evil", "vosk; rm -rf /"):
    check(f"{made_up!r} не опознан как пакет",
          models.find_package(made_up) is None)

print()
print("=== установленность решается импортом ===")
# Not by pip's exit code: it returns zero for "already satisfied" and for
# installs that leave nothing importable on this interpreter. The question
# is whether the core can import it now.
here = models.Package("probe", "Проба", "json-is-builtin", "json", "none", 0)
check("то, что импортируется, считается стоящим",
      models.have_package(here) is True)
missing = models.Package("probe2", "Проба", "nope", "no_such_module_here",
                         "none", 0)
check("а чего нет — не считается", models.have_package(missing) is False)

print()
print("=== pip сказал «готово», а импортировать нечего ===")
# The rule that matters, measured where the decision is made rather than on
# `have_package` alone: `pip` returns zero for "already satisfied" and for
# installs that leave nothing importable on this interpreter. Asked about
# the exit code, the first edition of this check stayed green while the
# decision was broken.


class Pretend:
    """A `pip` that succeeds and installs nothing."""

    returncode = 0
    stdout = iter(["Successfully installed nothing-0.0"])

    def wait(self):
        return 0

    def poll(self):
        return 0


ghost = models.Package("ghost", "Призрак", "nothing", "no_such_module_here",
                       "none", 0)
seen = []
subprocess.Popen = lambda *a, **k: Pretend()
try:
    models.Install(ghost, on_progress=seen.append)._run()
finally:
    subprocess.Popen = real_popen

check("такое не считается установленным",
      seen and seen[-1]["state"] == "failed",
      f"| {seen[-1]['state'] if seen else '—'}")
check("и причина названа", seen and seen[-1].get("error"),
      f"| {seen[-1].get('error', '') if seen else ''}")

print()
print("ИТОГО ошибок:", fails)
sys.exit(1 if fails else 0)
