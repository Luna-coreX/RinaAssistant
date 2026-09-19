# -*- coding: utf-8 -*-
"""
The full regression: one call, one report (plan item 4.0-I04).

By the end of the milestone there were about thirty checks, each started by
its own name. While there were five that worked; at thirty it stops
working — not because it is hard but because it has to be **remembered**. A
check that was forgotten is indistinguishable from one that does not exist:
the recorded-behaviour sessions were red for a week, and that was
discovered by accident.

What is here besides convenience.

**The list of checks is derived, not written by hand.** Every
`tools/test_*.py` and `tools/check_*.py` is a check; the generators are
checked by their own `--check`; the shell's modes are read from
`Startup.cs`. A hand-written list would part company with the catalogue at
the first new check — exactly as is already recorded about the error
catalogue in `test_wire.py`.

**What is not a check is named by name and with a reason.** Otherwise
"derived" turns into "derived, apart from what we forgot": a file that fell
out of both categories would pass silently. The regression fails on such a
file.

**A skip is visible and counted.** The shell's checks need `dotnet`; if it
is absent, saying "skipped" is more honest than showing a green total.
`--strict` makes a skip an error — for the build line, where there is
nothing to skip.

**What touches the machine is set apart.** `--check-voice` speaks aloud,
`--check-hover` moves the mouse, `--check-tray` creates an icon. Their
place is the `машина` group, and by default they do not run: a regression
that starts talking and moving the cursor in the middle of the working day
gets run once.

To run:
    python tools/regress.py               core and shell
    python tools/regress.py --group `ядро`  python only, no dotnet
    python tools/regress.py --all         including what touches the machine
    python tools/regress.py --strict      a skip counts as an error
    python tools/regress.py --list        only show what would be run
"""
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
os.chdir(ROOT)

from console import child_env, use_utf8
use_utf8()

TOOLS = os.path.join(ROOT, "tools")
SHELL_PROJECT = os.path.join("shell", "Rina.Shell", "Rina.Shell.csproj")
STARTUP = os.path.join("shell", "Rina.Shell", "Startup.cs")


# ---------------------------------------------------------------------------
# What is not a check
# ---------------------------------------------------------------------------
#: By name and with a reason.
#:
#: The list is not for tidiness but so that "derived" stays true. A file
#: that is not a check and is not named here is either a forgotten check or
#: a forgotten explanation; both are worth turning the regression red.
NOT_A_CHECK = {
    "_core_sandboxed.py": "запускатель ядра под песочницей, не проверка",
    "build_mockups.py": "собирает макеты, ничего не сверяет",
    "build_release.py": "собирает выпуск; сверяет его check_release.py",
    "console.py": "общая мелочь: вывод в UTF-8",
    "coreproc.py": "живое ядро в отдельном процессе; им говорят проверки",
    "nebula.py": "арифметика цвета живого фона; ею пользуются генератор и проверки",
    "regress.py": "этот файл",
    "retranslate.py": "правит комментарии по заданию",
    "sandbox.py": "песочница, которой пользуются проверки",
    "voice_bench.py": "стенд замеров: меряет, а не проверяет",
}

#: The checks that need a built release, and where it lies.
#:
#: Building a release inside the regression is not on: that is minutes,
#: the network and a quarter of a gigabyte on disk. But keeping quiet about
#: an unchecked installer is not on either, so without a release the check
#: does not disappear — it becomes "skipped", saying what would fix it.
NEEDS_RELEASE = {
    "check_release.py": os.path.join(ROOT, "dist", "Rina"),
}

#: Generators: their check is to compare what was generated with its source.
GENERATORS = ("gen_csharp_contract.py", "gen_shell_strings.py",
              "gen_site.py", "gen_xaml_tokens.py")

#: The checks that are not called by a file name.
BY_HAND = {
    "session.py": ["--replay-all"],
    # A pixel comparison needs a screenshot, and the screenshot is taken
    # by the shell itself. It is in the `снимок` group and is assembled
    # from two steps — see `render_checks`.
    "check_shell_render.py": None,
}

#: The finishes, each with its own screenshot.
#:
#: They are equals (`4.0-R08`), and checking one would mean checking a
#: fraction: their values differ, and they can drift apart independently.
#:
#: Read from the tokens rather than written out here. A hand-written tuple
#: is exactly what the header of this file warns about, and it caught up
#: with us: `graphite` arrived in `4.0b-A06` and would have been left
#: unchecked — silently, because a list that is short is not a list that is
#: wrong.
def _finishes() -> tuple[str, ...]:
    with open(os.path.join(ROOT, "docs", "design", "tokens.json"),
              encoding="utf-8") as handle:
        return tuple(json.load(handle)["finishes"])


FINISHES = _finishes()

#: The shell modes that touch the machine or the person.
#:
#: Not "slow" and not "fragile": they speak aloud, move the mouse and put
#: an icon in the tray. A regression that does that unasked in the middle
#: of a working day stops being run — and then it checks nothing.
TOUCHES_MACHINE = {"--check-voice", "--check-hover", "--check-tray",
                   "--check-audio", "--check-system",
                   # Asks Windows what is playing on this machine right now,
                   # and part of what it checks depends on the answer.
                   "--check-media"}


#: The interpreter the **core** runs on — and therefore the one its
#: checks have to run on.
#:
#: **The suite spent months checking a program that does not ship.**
#: `sys.executable` is whichever Python happened to start the
#: regression; the core is started by the shell, which picks the
#: shipped runtime, then `venv`, then `PATH` — and the models, the
#: voices and the sound are installed **there**. So checks that needed
#: `vosk`, `soundfile`, `av` or `edge_tts` printed "skipped" in small
#: print and went green for years of runs. A check that cannot run is
#: not a check that passes.
#:
#: The order is the shell's (`CoreLink.Interpreter`) **as it runs
#: here**. The shell prefers the runtime it ships, because on a
#: person's machine that one is the only one; in development there is
#: no `runtime` beside the built shell and it falls through to `venv`.
#: The packaged runtime is not left unchecked — `check_release.py`
#: asks it directly whether it can hear and speak — and pointing the
#: whole suite at `dist` would mean checking whatever was last built
#: rather than what is being written now.
def core_python():
    candidates = [
        os.path.join(ROOT, "venv", "Scripts", "python.exe"),
        os.path.join(ROOT, ".venv", "Scripts", "python.exe"),
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path
    return sys.executable


PYTHON = core_python()


class Check:
    """One check: its name, what runs it, and which group it is in."""

    def __init__(self, name, group, command, note="", skip=""):
        self.name = name
        self.group = group
        self.command = command
        self.note = note
        #: Non-empty means we do not run the check but name the reason.
        #: A skip has to explain itself: a "skipped" line without a "why"
        #: reads as "broken, but we did not look".
        self.skip = skip


def python_checks():
    """`tools/test_*.py`, `tools/check_*.py` and generators with a check."""
    found = []
    for name in sorted(os.listdir(TOOLS)):
        if not name.endswith(".py"):
            continue
        path = os.path.join("tools", name)
        if name in NOT_A_CHECK:
            continue
        if name in GENERATORS:
            found.append(Check(name, "ядро",
                               [PYTHON, path, "--check"],
                               "порождённое сходится с источником"))
            continue
        if name in BY_HAND:
            args = BY_HAND[name]
            if args is None:
                continue
            found.append(Check(name, "ядро", [PYTHON, path] + args))
            continue
        if name in NEEDS_RELEASE and not os.path.isdir(NEEDS_RELEASE[name]):
            # No release means nothing to check, and that is "skipped"
            # rather than "passed": a green line about an unchecked
            # installer is worse than a red one, because it is
            # believed.
            found.append(Check(name, "выпуск", [PYTHON, path],
                               skip="нет dist/Rina — "
                                    "python tools/build_release.py"))
            continue
        if name.startswith(("test_", "check_")) or name in (
                "conformance.py", "golden_runner.py"):
            found.append(Check(name, "ядро", [PYTHON, path]))
    return found


def unclassified():
    """
    Files that are not checks and are not named as such.

    That is the price of deriving the list: without this comparison
    "derived" means "derived from whatever matched the pattern", and a new
    tool with an unusual name drops out silently.
    """
    known = {c.name for c in python_checks()}
    out = []
    for name in sorted(os.listdir(TOOLS)):
        if not name.endswith(".py") or name in NOT_A_CHECK or name in known:
            continue
        if name in BY_HAND:            # named separately, see the `снимок` group
            continue
        out.append(name)
    return out


def shell_modes():
    """The `--check-*` modes the shell itself declares."""
    text = io.open(STARTUP, encoding="utf-8").read()
    return sorted(set(re.findall(r'"(--check-[a-z]+)"', text)))


def shell_checks():
    found = []
    for mode in shell_modes():
        group = "машина" if mode in TOUCHES_MACHINE else "оболочка"
        found.append(Check(mode, group,
                           ["dotnet", "run", "--project", SHELL_PROJECT,
                            "--", mode]))
    return found


def render_checks(shots_dir):
    """
    The drawn window against the tokens — in two steps.

    The screenshot is taken by the shell itself (`--shot`) and compared
    point by point by `check_shell_render.py`. In two steps because
    drawing and measuring are done by different things: WPF draws, python
    measures, and the only way to connect them is through a file.
    """
    found = []
    for finish in FINISHES:
        png = os.path.join(shots_dir, f"{finish}.png")
        found.append(Check(f"снимок {finish}", "снимок",
                           ["dotnet", "run", "--project", SHELL_PROJECT,
                            "--", "--shot", png, "--finish", finish]))
        found.append(Check(f"сверка {finish}", "снимок",
                           [PYTHON,
                            os.path.join("tools", "check_shell_render.py"),
                            png, finish]))
    return found


def all_checks(shots_dir):
    return python_checks() + shell_checks() + render_checks(shots_dir)


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------
def run(check, timeout):
    """Run it: (outcome, seconds, the last line, why it failed)."""
    if check.skip:
        return "пропущено", 0.0, check.skip, [], []
    started = time.monotonic()
    try:
        done = subprocess.run(check.command, capture_output=True, text=True,
                              encoding="utf-8", errors="replace",
                              env=child_env(), timeout=timeout)
    except FileNotFoundError:
        return "пропущено", 0.0, f"нет {check.command[0]}", [], []
    except subprocess.TimeoutExpired:
        return ("провал", time.monotonic() - started,
                f"не уложилась в {timeout} с", [])

    spent = time.monotonic() - started
    tail = ""
    for line in reversed((done.stdout or "").splitlines()):
        if line.strip():
            tail = line.strip()
            break
    # What actually failed, not only that something did.
    #
    # Until this was here the summary said "провал: --check-dialogue" and no
    # more, and finding out which line went red meant running the check by
    # hand — where it passed, because what broke it was the run's own order.
    # Half an hour of guessing at a suite that already knew the answer and
    # was not saying it.
    reasons = [line.strip() for line in (done.stdout or "").splitlines()
               if "FAIL" in line or "МАЛО" in line]
    if done.returncode != 0 and not reasons and (done.stderr or "").strip():
        reasons = [(done.stderr or "").strip().splitlines()[-1]]
    if done.returncode != 0 and not reasons:
        # Neither a red line nor a word on the error stream, and the
        # process still failed: that is a crash, not a check saying no.
        # Met exactly so — every check passed, then the process fell over
        # on the way out, and the summary said "провал" and nothing else.
        # An exit code is not much, but 0xC0000005 is a whole diagnosis.
        known = {3221225477: "0xC0000005 — обращение к чужой памяти",
                 3221225786: "0xC000013A — прервано с клавиатуры",
                 3221226356: "0xC0000374 — куча повреждена"}
        code = done.returncode & 0xFFFFFFFF
        reasons = [f"процесс упал: код {code} "
                   f"({known.get(code, 'смотреть вручную')})"]
    # What the check skipped **inside itself**, which the summary has
    # never shown. A section that says "пропущено: нет модели" in small
    # print and goes green is the same silence as a check that does not
    # run at all — and for a year that is exactly what the whole suite
    # was, running on an interpreter without the core's packages.
    # A skip line, not a check whose **name** contains the word: the
    # wire suite has "пропущено разрешённое: новое событие" among its
    # green lines, and counting those would turn this into noise on the
    # first run.
    inner = [line.strip() for line in (done.stdout or "").splitlines()
             if line.strip().startswith("пропущено")]
    return (("успех" if done.returncode == 0 else "провал"), spent, tail,
            reasons[:4], inner[:4])


def main(argv):
    wanted = {"ядро", "оболочка", "снимок"}
    if "--all" in argv:
        wanted.add("машина")
    if "--group" in argv:
        wanted = {argv[argv.index("--group") + 1]}
    strict = "--strict" in argv

    # Screenshots go into a temporary folder: the regression must not
    # leave pictures behind in the project tree.
    shots = tempfile.mkdtemp(prefix="rina-regress-")
    stray = unclassified()
    checks = [c for c in all_checks(shots) if c.group in wanted]

    if "--list" in argv:
        for c in checks:
            print(f"  {c.group:9} {c.name}")
        print(f"\nвсего: {len(checks)}")
        return 0

    print("=== полный регресс (4.0-I04) ===")
    # Which Python — out loud. It is the interpreter the core runs on
    # (see `core_python`), and when that turns out to be the wrong one,
    # this line is where it will be seen.
    print(f"     питон ядра: {PYTHON}")
    print(f"    групп: {', '.join(sorted(wanted))}, проверок: {len(checks)}")
    print()

    failed, skipped, inside, spent_total = [], [], [], 0.0
    for c in checks:
        # The shell has to raise the core and wait for the link; python
        # does not.
        timeout = 600 if c.group != "ядро" else 300
        verdict, spent, tail, reasons, passed_over = run(c, timeout)
        spent_total += spent
        mark = {"успех": "OK  ", "провал": "FAIL", "пропущено": "----"}[verdict]
        print(f"  {mark}  {c.name:26} {spent:6.1f} с  {tail[:60]}")
        if verdict == "провал":
            failed.append((c.name, reasons))
        elif verdict == "пропущено":
            skipped.append(f"{c.name} ({tail})")
        for line in passed_over:
            inside.append((c.name, line))

    print()
    if stray:
        print("НЕ РАЗОБРАНО: файлы, которые не проверка и не названы таковыми")
        for name in stray:
            print(f"    {name}")
        print("    добавьте в NOT_A_CHECK с причиной — или назовите проверкой")
        print()

    print(f"Проверок: {len(checks)}, провалов: {len(failed)}, "
          f"пропущено: {len(skipped)}, за {spent_total:.0f} с")
    for name, reasons in failed:
        print(f"    провал: {name}")
        for reason in reasons:
            print(f"        {reason[:110]}")
    for name in skipped:
        print(f"    пропущено: {name}")
    # Green, but with a hole in it. Named here because a section that
    # skips itself and stays silent is how a suite comes to check less
    # than it says it does.
    for name, line in inside:
        print(f"    внутри {name}: {line[:96]}")
    if skipped and not strict:
        print("    пропуск не считается ошибкой; --strict сделает его ею")

    shutil.rmtree(shots, ignore_errors=True)
    bad = bool(failed) or bool(stray) or (strict and (skipped or inside))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
