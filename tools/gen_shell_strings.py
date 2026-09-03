# -*- coding: utf-8 -*-
"""
Порождает `Strings.g.cs` из `interface.json` (`4.0-F08`).

Тот же приём, что у токенов дизайна и снимка контракта: один источник и
порождённый файл рядом с кодом, который его читает. Руками таблицу в C# не
пишут — разошлась бы с источником на первой же правке.

Запуск:
    python tools/gen_shell_strings.py           переписать Strings.g.cs
    python tools/gen_shell_strings.py --check   сверить, не трогая
"""
import io
import json
import os
import sys

from console import use_utf8

use_utf8()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE = os.path.join(ROOT, "shell", "Rina.Shell", "Strings", "interface.json")
TARGET = os.path.join(ROOT, "shell", "Rina.Shell", "Generated", "Strings.g.cs")

HEAD = """// Порождено tools/gen_shell_strings.py. Руками не править.
//
// Источник: shell/Rina.Shell/Strings/interface.json
//
// Ключ — русская строка (4.0-F08, ADR 0007): непереведённое место
// показывает осмысленный оригинал, а не имя ключа и не пустоту.

namespace Rina.Shell.Strings;

public static partial class Loc
{
    /// <summary>Переводы: строка оригинала — язык — перевод.</summary>
    public static readonly IReadOnlyDictionary<string,
        IReadOnlyDictionary<string, string>> Table =
        new Dictionary<string, IReadOnlyDictionary<string, string>>
        {
"""

TAIL = """        };
}
"""


def escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def render(table: dict) -> str:
    lines = [HEAD]
    for key in sorted(table, key=lambda k: (k.lower(), k)):
        row = table[key]
        if not row:
            continue                # без переводов строка живёт как есть
        lines.append(f'            ["{escape(key)}"] =\n')
        lines.append("                new Dictionary<string, string>\n")
        lines.append("                {\n")
        for language in sorted(row):
            lines.append(f'                    ["{escape(language)}"] = '
                         f'"{escape(row[language])}",\n')
        lines.append("                },\n")
    lines.append(TAIL)
    return "".join(lines)


def main(argv) -> int:
    with io.open(SOURCE, encoding="utf-8") as source:
        table = json.load(source)

    rendered = render(table)
    translated = sum(1 for row in table.values() if row)
    languages = sorted({lang for row in table.values() for lang in row})

    if "--check" in argv:
        if not os.path.isfile(TARGET):
            print("Strings.g.cs нет — породите его")
            return 1
        with io.open(TARGET, encoding="utf-8") as target:
            if target.read() != rendered:
                print("Strings.g.cs разошёлся с interface.json")
                print("    python tools/gen_shell_strings.py")
                return 1
        print(f"Strings.g.cs сходится с источником "
              f"({len(table)} строк, переведено {translated})")
        return 0

    os.makedirs(os.path.dirname(TARGET), exist_ok=True)
    with io.open(TARGET, "w", encoding="utf-8", newline="\n") as target:
        target.write(rendered)
    print(f"порождено: {os.path.relpath(TARGET, ROOT)}")
    print(f"  строк {len(table)}, с переводом {translated}, "
          f"языков {len(languages)}")
    for language in languages:
        covered = sum(1 for row in table.values() if language in row)
        print(f"    {language}: {covered / len(table):.0%}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
