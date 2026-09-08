# -*- coding: utf-8 -*-
"""
Comparing a milestone's boundaries with a snapshot: what came in, what
went out, and whether that was decided.

Plan item 4.0-S03. The list of what is in 4.0 and what is not is the
"Рубежи 4.0" section of the plan itself, and it is written in words. In
words it would have stayed: an item gets added in the same place the code
is written, in passing and in the same commit. Then the milestone grows not
by decision but by habit — and "we will do it in 4.0" turns into "4.0 will
never ship".

The task's wording is plain: **closed as long as the list does not change
silently.** So what is needed is not a document but a point of reference.
The snapshot is `docs/scope-4.0.json`; the comparison answers not "are the
boundaries right" but "what has changed since last time, and was it
intended".

Exactly one thing is allowed silently:

    an item was done: an open one became `ВЫПОЛНЕНО`

That is not a change of boundaries but work: the same list, moved along.

These require rewriting the snapshot deliberately:

    adding an item to a milestone, removing it from one
    renaming an item
    moving it to another milestone (`[port]` ↔ `[stable]` ↔ `[4.1+]`)
    changing its size estimate
    **undoing what was done**: `ВЫПОЛНЕНО` back to open

The last one has a line of its own because it looks harmless. A mark
removed means the item was reopened; that can be legitimate, but it has to
be learned from a person rather than from silence.

The size is compared because the size *is* a boundary: an item whose S
quietly became an L is a different item, even under the same name.

To run:
    python tools/check_scope.py            compare
    python tools/check_scope.py --update   rewrite the snapshot
"""

import io
import json
import os
import re
import sys

from console import use_utf8

use_utf8()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROADMAP = os.path.join(ROOT, "docs", "ROADMAP.md")
SNAPSHOT = os.path.join(ROOT, "docs", "scope-4.0.json")

#: How a mark in an item's line names a milestone. The mark is written
#: short (`[stable]`) while the milestone has a full name — and without
#: the mapping the item would settle under a key the summary does not
#: have, that is, drop out of the count silently.
BY_MARK = {"port": "4.0-port", "stable": "4.0-stable", "4.1+": "4.1+"}

#: The order in which to show the milestones. An unfamiliar one is
#: printed after them: a summary that keeps quiet about what was not
#: expected is the same silent change of boundaries, only from our side.
ORDER = ("4.0-port", "4.0-beta", "4.0-stable", "4.1+")

#: An item's line: **4.0-D04 · Конверт** — M — D03 — **[port]** — **ВЫПОЛНЕНО …**
#:
#: The tail is taken whole and parsed separately: items have it in
#: different shapes — some carry a milestone mark, some do not, some carry
#: a completion date. Demanding one shape would mean editing the plan for
#: the comparison's convenience.
TASK = re.compile(r"^\*\*(4\.0-[A-Z]\d+|V-\d+) · ([^*]+?)\*\*(.*)$", re.M)

#: The size estimate right after the name: "— M —" or "— L —".
SIZE = re.compile(r"^\s*—\s*([SML])\s*(?:—|$)")

#: Which milestone an item belongs to. With no mark, the one whose
#: section it stands in.
MARK = re.compile(r"\[(port|stable|4\.1\+)\]")


def milestones(text):
    """The plan's sections by milestone: name -> a piece of text."""
    heads = [(m.start(), m.group(1))
             for m in re.finditer(r"^# РУБЕЖ (\S+)", text, re.M)]
    out = {}
    for i, (at, name) in enumerate(heads):
        end = heads[i + 1][0] if i + 1 < len(heads) else len(text)
        out[name] = text[at:end]
    return out


def current():
    """The boundaries as the plan describes them right now."""
    text = io.open(ROADMAP, encoding="utf-8").read()
    scope = {}
    for name, body in milestones(text).items():
        for match in TASK.finditer(body):
            task, title, tail = match.group(1), match.group(2), match.group(3)
            size = SIZE.match(tail)
            mark = MARK.search(tail)
            scope[task] = {
                "title": title.strip(),
                "size": size.group(1) if size else "",
                # The mark beats the section: an item lying in the port
                # section with a [stable] mark belongs to stable — that is
                # how it is read.
                "milestone": (BY_MARK[mark.group(1)] if mark else name),
                "done": "ВЫПОЛНЕНО" in tail,
            }
    return scope


def diff(old, new):
    """Return (what was simply done; what changes the boundaries)."""
    progress, changed = [], []

    for task in sorted(set(new) - set(old)):
        changed.append(f"задача добавлена: {task} · {new[task]['title']}")
    for task in sorted(set(old) - set(new)):
        changed.append(f"задача убрана: {task} · {old[task]['title']}")

    for task in sorted(set(old) & set(new)):
        was, now = old[task], new[task]
        if was["title"] != now["title"]:
            changed.append(f"{task}: название «{was['title']}» "
                           f"→ «{now['title']}»")
        if was["milestone"] != now["milestone"]:
            changed.append(f"{task}: рубеж {was['milestone']} "
                           f"→ {now['milestone']}")
        if was["size"] != now["size"]:
            changed.append(f"{task}: размер {was['size'] or '—'} "
                           f"→ {now['size'] or '—'}")

        if was["done"] and not now["done"]:
            changed.append(f"{task}: сделанное отменено — задачу переоткрыли")
        elif not was["done"] and now["done"]:
            progress.append(f"{task} · {now['title']}")

    return progress, changed


def counts(scope):
    """How many are in each milestone, and how many of those are done."""
    out = {}
    for item in scope.values():
        was_done, total = out.get(item["milestone"], (0, 0))
        out[item["milestone"]] = (was_done + int(item["done"]), total + 1)
    return out


def main(argv):
    scope = current()

    if "--update" in argv:
        io.open(SNAPSHOT, "w", encoding="utf-8", newline="\n").write(
            json.dumps(scope, ensure_ascii=False, indent=2,
                       sort_keys=True) + "\n")
        print(f"Снимок переписан: задач {len(scope)}.")
        return 0

    if not os.path.isfile(SNAPSHOT):
        print("Снимка нет. Первый раз — снять точку отсчёта:")
        print("    python tools/check_scope.py --update")
        return 1

    old = json.load(io.open(SNAPSHOT, encoding="utf-8"))
    progress, changed = diff(old, scope)

    print("=== S03: границы рубежа против снимка ===")
    if not progress and not changed:
        print("  изменений нет")
    for line in progress:
        print("  сделано ", line)
    for line in changed:
        print("  ГРАНИЦА ", line)

    print()
    tally = counts(scope)
    shown = 0
    for name in list(ORDER) + sorted(set(tally) - set(ORDER)):
        done, total = tally.get(name, (0, 0))
        if total:
            shown += total
            print(f"  {name}: {done} из {total}")
    # The count has to add up: an item that fell into no milestone is
    # exactly a boundary that changed quietly, only noticed from our
    # side.
    if shown != len(scope):
        print(f"  ВНИМАНИЕ: задач {len(scope)}, а в рубежах {shown}")

    print()
    if changed:
        print(f"Границы изменились: {len(changed)}.")
        print("Это бывает законно, но должно быть решением, а не привычкой.")
        print("Если так и задумано — перепишите снимок тем же коммитом:")
        print("    python tools/check_scope.py --update")
        return 1

    if progress:
        print(f"Границы те же. Сделано с прошлого снимка: {len(progress)}.")
        print("Снимок стоит обновить тем же коммитом.")
    else:
        print("Границы те же.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
