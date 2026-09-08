# -*- coding: utf-8 -*-
"""
Сверка границ рубежа со снимком: что вошло, что вышло и было ли это решено.

Задача плана 4.0-S03. Список того, что входит в 4.0 и не входит, — раздел
«Рубежи 4.0» самого плана, и записан он словами. Словами он бы и остался:
задачу дописывают там же, где пишут код, между делом и в том же коммите.
Тогда рубеж расширяется не решением, а привычкой — и «сделаем в 4.0»
превращается в «4.0 никогда не выйдет».

Формулировка задачи прямая: **закрыта, пока список не меняется молча.**
Значит нужен не документ, а точка отсчёта. Снимок —
`docs/scope-4.0.json`; сверка отвечает не «правильные ли границы», а «что
изменилось с прошлого раза и было ли это намерением».

Разрешено молча — ровно одно:

    задача сделана: открытая стала **ВЫПОЛНЕНО**

Это не изменение границ, а работа: список тот же, продвинулись по нему.

Требует переписать снимок осознанно:

    добавить задачу в рубеж, убрать её оттуда
    переименовать задачу
    перенести её в другой рубеж (`[port]` ↔ `[stable]` ↔ `[4.1+]`)
    изменить оценку размера
    **отменить сделанное**: ВЫПОЛНЕНО обратно в открытую

Последнее — отдельной строкой, потому что выглядит безобидно. Снятая
пометка означает, что задачу переоткрыли; это бывает законно, но узнать об
этом надо от человека, а не из молчания.

Размер сверяется, потому что он и есть граница: задача, у которой S тихо
стала L, — это другая задача, даже если название прежнее.

Запуск:
    python tools/check_scope.py            сверить
    python tools/check_scope.py --update   переписать снимок
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

#: Как пометка в строке задачи называется рубежом. Пометка пишется коротко
#: (`[stable]`), а рубеж зовётся полно — и без приведения задача осела бы в
#: ключе, которого нет в сводке, то есть пропала бы из счёта молча.
BY_MARK = {"port": "4.0-port", "stable": "4.0-stable", "4.1+": "4.1+"}

#: В каком порядке показывать рубежи. Незнакомый допечатывается следом:
#: сводка, которая молчит о том, чего не ждали, — это та же тихая правка
#: границ, только с нашей стороны.
ORDER = ("4.0-port", "4.0-beta", "4.0-stable", "4.1+")

#: Строка задачи: **4.0-D04 · Конверт** — M — D03 — **[port]** — **ВЫПОЛНЕНО …**
#:
#: Хвост забирается целиком и разбирается отдельно: у задач он разной формы —
#: где-то есть пометка рубежа, где-то нет, где-то стоит дата выполнения.
#: Требовать одной формы значило бы править план ради удобства сверки.
TASK = re.compile(r"^\*\*(4\.0-[A-Z]\d+|V-\d+) · ([^*]+?)\*\*(.*)$", re.M)

#: Оценка размера сразу после названия: «— M —» или «— L —».
SIZE = re.compile(r"^\s*—\s*([SML])\s*(?:—|$)")

#: В какой рубеж отнесена задача. Нет пометки — в тот, в чьём разделе стоит.
MARK = re.compile(r"\[(port|stable|4\.1\+)\]")


def milestones(text):
    """Разделы плана по рубежам: имя -> кусок текста."""
    heads = [(m.start(), m.group(1))
             for m in re.finditer(r"^# РУБЕЖ (\S+)", text, re.M)]
    out = {}
    for i, (at, name) in enumerate(heads):
        end = heads[i + 1][0] if i + 1 < len(heads) else len(text)
        out[name] = text[at:end]
    return out


def current():
    """Границы, как их описывает план прямо сейчас."""
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
                # Пометка сильнее раздела: задача, лежащая в разделе port с
                # пометкой [stable], относится к stable — так её и читают.
                "milestone": (BY_MARK[mark.group(1)] if mark else name),
                "done": "ВЫПОЛНЕНО" in tail,
            }
    return scope


def diff(old, new):
    """Вернуть (то, что просто сделано; то, что меняет границы)."""
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
    """Сколько в каком рубеже и сколько из этого сделано."""
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
    # Счёт обязан сойтись: задача, не попавшая ни в один рубеж, — это как раз
    # тихо изменившаяся граница, только замеченная с нашей стороны.
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
