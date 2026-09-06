# -*- coding: utf-8 -*-
"""
The comparison: every 3.1.0 action is reachable through the protocol.

Plan item 4.0-F04, but the check is needed before the pages — without it a
page gets written, runs into a missing method, and the protocol is written
on the fly.

`tools/check_design.py` already checks that every action from the surface
inventory has a **place** in the new information architecture. That is not
enough. A place answers the question "where is the button", while the
protocol answers the question "what will happen when it is pressed". A whole
gulf fits between them: the button is drawn, the section exists, and there
is no method for the shell to do it with.

The first run found exactly such a gulf, six capabilities wide: the list of
user commands, creating and editing them, switching them on, importing and
exporting, and the whole history — viewing, clearing, exporting. The
4.0-port boundary rule forbids losing capabilities; without this check they
would have been lost in silence, because what is lost is not a button but
the ability to do anything at all on a press.

To run:
    python tools/check_surface_reachable.py
"""

import os
import sys

from console import use_utf8

use_utf8()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

SURFACE = os.path.join(ROOT, "docs", "SURFACE-3.1.0.md")

fails = 0


def check(label, cond, detail=""):
    global fails
    if not cond:
        fails += 1
    print(("OK   " if cond else "FAIL "), label, detail)


#: What the shell will do the thing a person pressed with. The key is the
#: beginning of the action's line from the inventory; the value is the
#: protocol methods without which it cannot be done.
#:
#: An empty list means no method is needed: the action belongs entirely to
#: the shell. There are not many of those, and each is explained.
NEEDS: dict[str, list[str]] = {
    "Экспорт команд": ["commands.export"],
    "Импорт команд": ["commands.import"],
    "Создать, изменить, удалить команду": ["commands.list", "commands.save",
                                           "commands.delete"],
    "Включить или выключить команду": ["commands.set_enabled"],
    "Экспорт истории": ["history.export"],
    "Очистить историю": ["history.clear"],
    "Установить плагин из папки или архива": ["plugins.install"],
    "Включить или выключить плагин": ["plugins.set_enabled"],
    "Настройки плагина": ["plugins.page", "plugins.action"],
    "Проверить голос": ["speech.say"],
    "Проверить микрофон": [],           # the microphone is the shell's (4.0-F09)
    "Проверить связь с моделью": ["settings.set"],
    "Проверить модели Piper": ["settings.get"],
    "Выбрать модель Vosk": ["settings.set"],
    "Добавить папку с программами": ["settings.set"],
    "Обновить список программ": ["apps.index"],
    "Забыть выученные соответствия": ["settings.set"],
    "Открыть папку журналов": [],       # the shell opens the folder
    "Сбросить настройки": ["settings.set"],
    "Проверить обновления сейчас": [],  # updates are block U, a road of their own
    "Назначить любую из семи комбинаций": ["settings.set"],
    "Все настройки без исключения": ["settings.describe", "settings.get",
                                     "settings.set"],
    "Свернуть, развернуть, закрыть окно": [],   # the window belongs to the shell
}


def actions() -> list[str]:
    with open(SURFACE, encoding="utf-8") as f:
        text = f.read()
    start = text.index("## 3. Доступно только отсюда")
    end = text.index("## 4.", start)
    found = []
    for line in text[start:end].split("\n"):
        if line.startswith("|") and not line.startswith("|---"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if len(cells) >= 2 and not cells[0].startswith("Действие"):
                found.append(cells[0])
    return found


def main() -> int:
    from core.wire.handshake import BASE_METHODS, CAPABILITIES

    methods = set(BASE_METHODS)
    for capability in CAPABILITIES.values():
        methods |= set(capability.methods)

    print("=== F04: каждое действие достижимо через протокол ===")
    rows = actions()
    check("инвентарь поверхности прочитан", len(rows) >= 20,
          f"| действий: {len(rows)}")

    undescribed = [a for a in rows if a not in NEEDS]
    check("для каждого действия сказано, чем оно делается", not undescribed,
          f"| не описано: {undescribed}")

    missing: dict[str, list[str]] = {}
    for action in rows:
        need = NEEDS.get(action, [])
        gap = [m for m in need if m not in methods]
        if gap:
            missing[action] = gap

    check("все нужные методы есть в протоколе", not missing)
    if missing:
        print()
        print("     Недостижимо через протокол:")
        for action, gap in missing.items():
            print(f"       · {action}: нет {', '.join(gap)}")

    covered = sum(1 for a in rows if NEEDS.get(a))
    print(f"     действий, требующих протокола: {covered} из {len(rows)}")

    print()
    print("ИТОГО ошибок:", fails)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
