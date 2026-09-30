# -*- coding: utf-8 -*-
"""
Replacing blocks of comments by line numbers.

The comments are translated by a human (or a model) and put in place by a
machine: editing a thousand blocks in a hundred files by hand is a way of
one day eating a line of code along with a comment.

The tool **refuses** to touch a block containing even one line that does not
look like a comment. That is its whole point: not "replace the text" but
"replace the text, having made sure it is a comment".

The task format is JSON:

    {"path/to/file.cs": [[12, 18, "new text\nsecond line", "anchor"], ...]}

Line numbers start at one, the end is inclusive, as `Read` shows them. The
fourth element is the **anchor**: a piece of text that must occur in the
block being replaced. Without it, a range that has shifted by a couple of
lines will silently replace the neighbouring comment: the "this is a
comment" check does not catch that, because the neighbouring block is a
comment too. That is how the description of the data schema in `Updater.cs`
moved inside somebody else's condition.

To run:
    python tools/retranslate.py task.json
    python tools/retranslate.py task.json --dry   # only show
"""

import io
import json
import sys

#: What a comment line begins with in each language. A line inside a
#: docstring begins with nothing — there is a separate check for that.
STARTS = ("#", "//", "///", "<!--", "*", "-->", '"""', "'''")


def looks_like_comment(line: str, inside_doc: bool) -> bool:
    """
    Does the line look like part of a comment.

    Inside a docstring or a block comment any line will do except an empty
    one: there the text is the content. Outside — only one beginning with a
    known mark.
    """
    stripped = line.strip()
    if not stripped:
        return True
    if inside_doc:
        return True
    return stripped.startswith(STARTS)


def block_is_comment(lines: list[str], start: int, end: int) -> tuple[bool, str]:
    """Is the whole block [start, end] a comment. Returns (yes, the reason)."""
    inside_doc = False
    for number in range(start, end + 1):
        line = lines[number - 1]
        stripped = line.strip()

        # A triple quote both opens and closes a docstring; there may be
        # two on one line — then the docstring began and ended right there.
        quotes = stripped.count('"""') + stripped.count("'''")
        if quotes % 2 == 1:
            inside_doc = not inside_doc
            continue

        # An XML comment is opened and closed by different marks, and inside
        # it a line begins with nothing: `<!--` on its own line, the text on
        # the following ones. Without this a multi-line comment in XAML was
        # refused on its very second line — and that is exactly the form
        # everything long is written in inside markup.
        # `startswith` precisely: a line like `<Border/> <!-- explanation` is
        # code with a comment on its tail, and it must not be skipped.
        opens = stripped.startswith("<!--") and "-->" not in stripped[4:]
        closes = stripped.endswith("-->")
        if opens:
            inside_doc = True
            continue
        if closes and inside_doc:
            inside_doc = False
            continue

        if not looks_like_comment(line, inside_doc):
            return False, f"строка {number}: {stripped[:60]!r}"
    return True, ""


def apply(task: dict, dry: bool = False) -> int:
    changed = failed = 0
    for path, blocks in task.items():
        lines = io.open(path, encoding="utf-8").read().split("\n")

        # Back to front: a replacement changes the numbering below it, and
        # editing from the top down would shift every following block.
        for block in sorted(blocks, key=lambda b: -b[0]):
            start, end, text = block[0], block[1], block[2]
            anchor = block[3] if len(block) > 3 else ""

            ok, why = block_is_comment(lines, start, end)
            if not ok:
                print(f"ОТКАЗ {path}:{start}-{end} — не комментарий, {why}")
                failed += 1
                continue

            # The anchor answers the second question: not "is this a
            # comment" but "is it the right one". The first question on its
            # own lets a shift onto the neighbouring block through — that is
            # a comment too, after all, and the substitution passes in
            # silence. That is how the description of the data schema in
            # `Updater.cs` moved inside somebody else's condition.
            if anchor and anchor not in "\n".join(lines[start - 1:end]):
                print(f"ОТКАЗ {path}:{start}-{end} — не найден якорь "
                      f"{anchor!r}")
                failed += 1
                continue
            if dry:
                print(f"  {path}:{start}-{end} → {len(text.splitlines())} строк")
                continue
            lines[start - 1:end] = text.split("\n")
            changed += 1

        if not dry:
            io.open(path, "w", encoding="utf-8", newline="").write(
                "\n".join(lines))

    print(f"заменено блоков: {changed}, отказов: {failed}")
    return 1 if failed else 0


def main(argv) -> int:
    if not argv:
        print(__doc__)
        return 2
    task = json.load(io.open(argv[0], encoding="utf-8"))
    return apply(task, dry="--dry" in argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
