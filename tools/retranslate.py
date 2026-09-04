# -*- coding: utf-8 -*-
"""
Замена блоков комментариев по номерам строк.

Комментарии переводятся человеком (или моделью), а подставляются машиной:
ручная правка тысячи блоков в сотне файлов — это способ однажды съесть
строку кода вместе с комментарием.

Инструмент **отказывается** трогать блок, в котором есть хоть одна строка,
не похожая на комментарий. Это и есть его смысл: не «заменить текст», а
«заменить текст, убедившись, что это комментарий».

Формат задания — JSON:

    {"путь/к/файлу.cs": [[12, 18, "new text\\nsecond line"], ...]}

Номера строк — от единицы, конец включительно, как их показывает `Read`.

Запуск:
    python tools/retranslate.py задание.json
    python tools/retranslate.py задание.json --dry   # только показать
"""

import io
import json
import sys

#: Чем начинается строка комментария в каждом языке. Строка внутри
#: докстроки не начинается ничем — для неё есть отдельная проверка.
STARTS = ("#", "//", "///", "<!--", "*", "-->", '"""', "'''")


def looks_like_comment(line: str, inside_doc: bool) -> bool:
    """
    Похожа ли строка на часть комментария.

    Внутри докстроки или блочного комментария годится любая строка, кроме
    пустой: там текст и есть содержимое. Снаружи — только начинающаяся с
    известного знака.
    """
    stripped = line.strip()
    if not stripped:
        return True
    if inside_doc:
        return True
    return stripped.startswith(STARTS)


def block_is_comment(lines: list[str], start: int, end: int) -> tuple[bool, str]:
    """Весь ли блок [start, end] — комментарий. Возвращает (да, причина)."""
    inside_doc = False
    for number in range(start, end + 1):
        line = lines[number - 1]
        stripped = line.strip()

        # Тройная кавычка открывает и закрывает докстроку; в одной строке
        # их может быть две — тогда докстрока началась и кончилась тут же.
        quotes = stripped.count('"""') + stripped.count("'''")
        if quotes % 2 == 1:
            inside_doc = not inside_doc
            continue

        if not looks_like_comment(line, inside_doc):
            return False, f"строка {number}: {stripped[:60]!r}"
    return True, ""


def apply(task: dict, dry: bool = False) -> int:
    changed = failed = 0
    for path, blocks in task.items():
        lines = io.open(path, encoding="utf-8").read().split("\n")

        # Сзади наперёд: замена меняет нумерацию ниже себя, и правка
        # сверху вниз сдвинула бы все последующие блоки.
        for start, end, text in sorted(blocks, key=lambda b: -b[0]):
            ok, why = block_is_comment(lines, start, end)
            if not ok:
                print(f"ОТКАЗ {path}:{start}-{end} — не комментарий, {why}")
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
