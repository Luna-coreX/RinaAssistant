# -*- coding: utf-8 -*-
"""
The checks' output does not depend on the console's code page.

Found by a check that failed only sometimes: `test_service.py` printed the
list of languages, "Español" among them, and on a console with a Windows
code page the letter "ñ" caused a `UnicodeEncodeError` — right inside the
`print` of the result's caption. A check that is green under one run and red
under another is worse than none: it teaches one not to believe checks.

The same with a child process: the core writes to the error stream in
Russian, and a parent reading it as UTF-8 tripped over code-page bytes.
There is one understanding for everyone — UTF-8 everywhere — and here it is
put into effect.
"""
import os
import sys


def use_utf8() -> None:
    """Our own output — in UTF-8, whatever is set in the console."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            # The stream is substituted or already closed — no reason to fail a check.
            pass


def child_env(**extra) -> dict:
    """
    The environment for a child process: it writes in UTF-8 too.

    Otherwise the parent, reading the output as UTF-8, gets code-page bytes
    and fails in the reading thread — far from the place where it went
    wrong.
    """
    return dict(os.environ, PYTHONIOENCODING="utf-8", **extra)
