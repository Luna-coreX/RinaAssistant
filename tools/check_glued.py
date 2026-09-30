# -*- coding: utf-8 -*-
"""
Adjacent string literals that lost the space between them.

Python joins `"раз." "два"` into `раз.два` and says nothing. In a long
prose constant split across lines — a persona, a prompt, a help text —
the seam is invisible to the eye: every line reads correctly on its
own, and only the joined result is wrong.

**Found in `DEFAULT_PERSONA`.** Seventeen lines, each ending with a full
stop and the next starting with a capital, produced a wall of
«…ассистент Luna.Общайся тепло…» for the model to read. Nothing was
broken, nothing was logged, and the text looked right in the editor.

The rule is narrow on purpose. It looks only at seams where both sides
read as prose, because literals split without a space are ordinary and
correct in the places that are not prose — a long URL, a regular
expression, a path assembled from parts.

To run:
    python tools/check_glued.py
"""
import io
import os
import sys
import tokenize

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

#: Where to look: the project's own Python, named rather than excluded.
#:
#: Excluding by name was the first attempt and it let a second virtual
#: environment through — the folder is called `venv (3.14)`, and a list
#: of names to skip matches what it was told to match. Forty-seven
#: findings came back, every one of them from somebody else's library.
#: Naming what is ours cannot go wrong that way.
LOOK_IN = ("core", "voice", "tools", "plugins", "packaging")

#: Punctuation that ends a sentence. A letter straight after one of
#: these is the shape the persona had.
ENDINGS = ".,;:!?…»"


def looks_like_prose(text):
    """Is this piece of text a sentence rather than a path or a pattern."""
    if len(text) < 12:
        return False
    if " " not in text.strip():
        return False
    # Patterns, addresses and format strings are joined without spaces on
    # purpose, and often enough that flagging them would bury the rest.
    for mark in ("://", "\\", "%s", "{}", "  ", "\t"):
        if mark in text:
            return False
    return True


#: Python written inside a string, for `python -c` and the like.
#:
#: It reads as prose to every test above — it has spaces, it is long
#: enough, it has no slashes — and a semicolon there separates
#: statements rather than clauses, so nothing is missing at the seam.
CODE_MARKS = ("import ", "print(", "sys.", "lambda ", "def ", "; ")


def looks_like_code(text):
    return any(mark in text for mark in CODE_MARKS)


def decoded(token_text):
    """The literal's content, or None if it cannot be read safely."""
    try:
        value = eval(token_text, {"__builtins__": {}}, {})  # noqa: S307
    except Exception:
        return None
    return value if isinstance(value, str) else None


def seams(path):
    """Every adjacent-literal seam in one file: (line, left, right)."""
    found = []
    try:
        with tokenize.open(path) as source:
            tokens = [t for t in tokenize.generate_tokens(source.readline)
                      if t.type not in (tokenize.NL, tokenize.NEWLINE,
                                        tokenize.COMMENT, tokenize.INDENT,
                                        tokenize.DEDENT)]
    except (SyntaxError, tokenize.TokenError, UnicodeDecodeError):
        return found
    for at in range(len(tokens) - 1):
        one, two = tokens[at], tokens[at + 1]
        if one.type != tokenize.STRING or two.type != tokenize.STRING:
            continue
        left, right = decoded(one.string), decoded(two.string)
        if left is None or right is None:
            continue
        found.append((two.start[0], left, right))
    return found


def glued(left, right):
    """Does this seam swallow a space that the text needed."""
    if not left or not right:
        return False
    if left.endswith((" ", "\n", "-", "(", "«", "/")):
        return False
    if right.startswith((" ", "\n", ")", ",", ".", "»")):
        return False
    if not (looks_like_prose(left) and looks_like_prose(right)):
        return False
    if looks_like_code(left) or looks_like_code(right):
        return False
    # A letter straight after a sentence ending, or straight after
    # another letter: both mean two words became one.
    return left[-1] in ENDINGS or (left[-1].isalpha() and right[0].isalpha())


def walk():
    for name in sorted(os.listdir(ROOT)):
        if name.endswith(".py") and os.path.isfile(os.path.join(ROOT, name)):
            yield os.path.join(ROOT, name)
    for top in LOOK_IN:
        start = os.path.join(ROOT, top)
        if not os.path.isdir(start):
            continue
        for folder, dirs, files in os.walk(start):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for name in sorted(files):
                if name.endswith(".py"):
                    yield os.path.join(folder, name)


def main():
    from console import use_utf8

    use_utf8()
    bad = []
    files = 0
    for path in walk():
        files += 1
        for line, left, right in seams(path):
            if glued(left, right):
                bad.append((path, line, left, right))

    print("=== склейка строк без пробела ===")
    print("    (файлов просмотрено: %d)" % files)
    print()
    for path, line, left, right in bad:
        where = os.path.relpath(path, ROOT)
        print("FAIL  %s:%d" % (where, line))
        print("        …%s" % left[-40:])
        print("        %s…" % right[:40])
        print("      склеится в: …%s%s…" % (left[-20:], right[:20]))
        print()
    if not bad:
        print("OK    ни одной")
    print()
    print("ИТОГО ошибок:", len(bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
