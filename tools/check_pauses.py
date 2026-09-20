# -*- coding: utf-8 -*-
"""
A check does not sleep instead of waiting.

`--check-motion` measures that movement is visible in time, and
`test_speech.py` was rewritten because it measured the machine. This is
the same rule pointed at the checks themselves: **a pause is a guess
about how long a machine takes, and it is wrong in both directions at
once.** Too short, and the check goes red about a program that is
perfectly fine — that is how `--check-home` and `--check-core` each
failed once under a full regression, having measured nothing. Too long,
and every other run spends the difference asleep.

`Until(...)` is the answer, and it has been in the shell all along. The
trouble is not that nobody knew: it is that a pause is one line and
writing the condition is two, so the file grew a hundred and sixty-eight
pauses while nothing counted them.

So they are counted. The number here may go **down** and not up: a new
pause standing in front of an assertion has to displace an old one or
be written as a wait. It is a debt named out loud rather than a rule
pretending the debt is not there.

**What is not counted.** A pause that *is* the measurement — "and after
two and a half seconds the window is still there", "and in a second it
moves noticeably" — asks about the passage of time itself, and `Until`
would take the question away. Those are marked in the code with
`// measured`, on the line, so that the mark stands beside the thing it
excuses rather than in a list somewhere else that drifts.

To run:
    python tools/check_pauses.py
"""
import io
import os
import re
import sys

from console import use_utf8

use_utf8()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHELL = os.path.join(ROOT, "shell", "Rina.Shell")

#: A pause, and how long it sleeps for.
PAUSE = re.compile(r"await Task\.Delay\((\d+)\)")

#: The mark that says this pause is the measurement.
MEASURED = "// measured"

#: An assertion, or a branch that reads what the pause was waiting for.
LOOKS = re.compile(r"\bCheck\(|\bwindow\.CurrentPage\b|\bis Pages\.")

#: How many are left. Only ever smaller.
#:
#: 106 when this was written, down from 119. Seven page switches became
#: `OpenedAsync`, which waits for the page instead of guessing at it;
#: four more turned out to be measurements and are marked as such. The
#: suite sleeps 63.3 seconds instead of 72.5 — the nine seconds were
#: pure margin, and the flakiness went with them.
ALLOWED = 106

fails = 0


def check(label, ok, detail=""):
    global fails
    if not ok:
        fails += 1
    print(("OK   " if ok else "FAIL "), label, detail)


def sources():
    for base, dirs, files in os.walk(SHELL):
        dirs[:] = [d for d in dirs if d not in {"obj", "bin"}]
        for name in files:
            if name.endswith(".cs"):
                yield os.path.join(base, name)


def main() -> int:
    guessed = []
    asleep = 0
    for path in sources():
        lines = io.open(path, encoding="utf-8").read().split("\n")
        short = os.path.relpath(path, ROOT)
        for at, line in enumerate(lines):
            found = PAUSE.search(line)
            if not found:
                continue
            asleep += int(found.group(1))
            if MEASURED in line:
                continue
            # A pause is suspect when something reads the world just
            # after it: that is a wait wearing a pause's clothes.
            if any(LOOKS.search(one) for one in lines[at + 1:at + 6]):
                guessed.append("%s:%d (%s мс)"
                               % (short, at + 1, found.group(1)))

    print("=== проверка не спит вместо того, чтобы ждать ===")
    print("  пауз перед утверждением: %d, потолок %d"
          % (len(guessed), ALLOWED))
    print("  суммарно сна в проверках: %.1f с" % (asleep / 1000))

    check("пауз не стало больше", len(guessed) <= ALLOWED,
          "| стало %d при потолке %d; новая пауза перед утверждением "
          "обязана вытеснить старую или быть написана ожиданием"
          % (len(guessed), ALLOWED))
    # A ceiling nobody lowers is a ceiling nobody reads. When the count
    # drops, the number here follows it in the same commit — otherwise
    # the slack quietly becomes room for the next pause.
    check("потолок опущен до достигнутого", len(guessed) >= ALLOWED,
          "| осталось %d при потолке %d — опустите ALLOWED"
          % (len(guessed), ALLOWED))

    print()
    print("ИТОГО ошибок:", fails)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
