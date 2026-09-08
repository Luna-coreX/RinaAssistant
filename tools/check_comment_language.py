# -*- coding: utf-8 -*-
"""
Comments in the code are written in English. Checked by parsing, not by
hunting for letters.

The rule is simple and not a matter of taste: **code is read in English,
the product speaks Russian**. A Russian comment in a file where everything
else has been translated is not a lapse of taste but half a file in another
language — and whoever comes here next will write the same way, because
that is the example in front of them.

The check appeared after the translation of the codebase had been declared
finished while some seven hundred Russian blocks were still in the tree.
Declaring work finished is easy; the only way to check it is this.

**Three things that must not be confused here.**

`1.` **Interface strings and Rina's lines stay Russian.** They are not
comments: the labels in the window are keys of `interface.json`, the lines
are keys of the dictionary in `core/i18n.py`. That is why the syntax is
parsed rather than Cyrillic searched for: from Python we take comment
tokens and docstrings, from C# and XAML the lines that begin with a comment
marker.

`2.` **A quotation inside a comment is data.** "напомни когда открою студию
проверить почту" in a comment next to the phrase parsing is not the text of
the comment but an example of what is being parsed. Translating it would
make the comment wrong. So everything in quotation marks of any kind is cut
out first, and only the remainder is checked for Cyrillic.

**A comment is judged as a block, not line by line.** A quotation easily
spans two lines, and a line-by-line rule would demand the translation of
half a quotation — that is, it would demand making the comment wrong. Run
line by line, this check reported ten such places in `voice/reminders.py`
alone, every one of them a false alarm.

`3.` **Documentation stays Russian in full.** `docs/`, `README.md` and the
rest of the prose are not covered here: they are not code.

What the check does **not** catch, and must not: English written badly.
Language is a property of a line, quality is a judgement, and automation
would guess the second from the words — that is, wrongly and silently.

To run:
    python tools/check_comment_language.py
    python tools/check_comment_language.py --list   the places only
"""

import io
import os
import re
import sys
import tokenize

from console import use_utf8

use_utf8()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: Where we do not go. `dist` and `venv` are not our code; `archive` is what
#: has already been moved out of the way; `Generated` is generated, and is
#: fixed by fixing its generator.
SKIP_DIRS = {
    ".git", ".claude", "__pycache__", "archive", "bin", "obj", "dist",
    "node_modules", "runtime", "Generated", "packages",
}

#: Two Cyrillic letters in a row — that is a word. One on its own is the
#: letter itself, mentioned as data: `textmatch.py` says its docstring
#: brings a phrase to a comparable form by "case, ё, punctuation", and the
#: `ё` there is the thing being described, not Russian prose.
CYRILLIC = re.compile(r"[а-яёА-ЯЁ]{2,}")

#: Quotation marks inside which Cyrillic is an example, not the comment's
#: own text. Guillemets, typewriter doubles, singles and backticks: all four
#: occur in this project's comments.
QUOTED = re.compile(r"«[^»]*»|\"[^\"]*\"|'[^']*'|`[^`]*`")

#: What a comment line starts with, per language.
MARKERS = {
    ".cs": ("///", "//", "*", "/*"),
    ".xaml": ("<!--", "-->", "*"),
}


def own_text(block: str) -> str:
    """The comment's own words: everything quoted is cut out."""
    return QUOTED.sub(" ", block)


def python_blocks(path):
    """(line, block) for a Python file's comments and docstrings."""
    blocks = []
    run, run_at, run_line = [], 0, -2
    with io.open(path, "rb") as handle:
        try:
            for token in tokenize.tokenize(handle.readline):
                if token.type == tokenize.COMMENT:
                    # Consecutive `#` lines are one comment: a quotation
                    # spans them freely, and judging them apart would split
                    # a quotation in half.
                    if token.start[0] == run_line + 1:
                        run.append(token.string.lstrip("#").strip())
                    else:
                        if run:
                            blocks.append((run_at, " ".join(run)))
                        run, run_at = [token.string.lstrip("#").strip()], \
                            token.start[0]
                    run_line = token.start[0]
                elif token.type == tokenize.STRING:
                    head = token.line.lstrip()
                    if head.startswith(('"""', "'''", 'r"""', "r'''")):
                        # Exactly the delimiter, not a class of characters.
                        # A docstring that opens with a quotation begins
                        # with four quote marks in a row, and stripping
                        # them all took away the example's own opening
                        # quote — after which the quotation could not be
                        # paired, and its text was read as the comment's.
                        body = token.string
                        if body[:1] in "rRbBuU":
                            body = body[1:]
                        if body[:3] in ('"""', "'''"):
                            body = body[3:-3]
                        blocks.append((token.start[0], body))
        except (tokenize.TokenError, SyntaxError, IndentationError) as exc:
            blocks.append((0, f"<unparsable: {exc}>"))
    if run:
        blocks.append((run_at, " ".join(run)))
    return blocks


def marked_blocks(path, markers):
    """(line, block) where a comment is known by how the line starts."""
    blocks = []
    run, run_at, run_line = [], 0, -2
    for number, line in enumerate(io.open(path, encoding="utf-8"), 1):
        stripped = line.strip()
        if not stripped.startswith(markers):
            continue
        body = stripped.lstrip("/*<!-").rstrip("->").strip()
        if number == run_line + 1:
            run.append(body)
        else:
            if run:
                blocks.append((run_at, " ".join(run)))
            run, run_at = [body], number
        run_line = number
    if run:
        blocks.append((run_at, " ".join(run)))
    return blocks


def offenders(path: str):
    """The places in this file where a comment is written in Russian."""
    suffix = os.path.splitext(path)[1]
    if suffix == ".py":
        blocks = python_blocks(path)
    elif suffix in MARKERS:
        blocks = marked_blocks(path, MARKERS[suffix])
    else:
        return []
    return [(line, " ".join(block.split())[:100])
            for line, block in blocks
            if CYRILLIC.search(own_text(block))]


def walk():
    """The project's code — no generated, vendored or archived files."""
    for base, dirs, files in os.walk(ROOT):
        dirs[:] = sorted(d for d in dirs
                         if d not in SKIP_DIRS and not d.startswith("venv"))
        for name in sorted(files):
            if name.endswith((".py", ".cs", ".xaml")):
                yield os.path.join(base, name)


def main(argv) -> int:
    only_list = "--list" in argv
    places, files = 0, 0

    print("=== comments in the code are in English ===")
    for path in walk():
        found = offenders(path)
        if not found:
            continue
        files += 1
        places += len(found)
        rel = os.path.relpath(path, ROOT).replace("\\", "/")
        print(f"  FAIL  {rel}: {len(found)}")
        if only_list:
            for line, text in found:
                print(f"        {line}: {text}")

    if not places:
        print("  OK    ни одного русского комментария")

    print()
    print(f"Файлов: {files}, мест: {places}")
    print("ИТОГО ошибок:", 1 if places else 0)
    return 1 if places else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
