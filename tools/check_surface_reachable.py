# -*- coding: utf-8 -*-
"""
Сверка: каждое действие 3.1.0 достижимо через протокол.

Задача плана 4.0-F04, но проверка нужна раньше страниц — без неё страницу
пишут, упираются в отсутствующий метод и дописывают протокол на ходу.

`tools/check_design.py` уже проверяет, что у каждого действия из инвентаря
поверхности есть **место** в новой информационной архитектуре. Этого мало.
Место — это ответ на вопрос «где кнопка», а протокол отвечает на вопрос
«что произойдёт, когда её нажмут». Между ними умещается целая пропасть:
кнопка нарисована, раздел есть, а метода, которым оболочка это сделает, нет.

Первый прогон нашёл ровно такую пропасть в шесть возможностей: список
пользовательских команд, их создание и правка, включение, импорт и экспорт,
и вся история — просмотр, очистка, выгрузка. Правило рубежа 4.0-port
запрещает терять возможности; без этой проверки они терялись бы молча,
потому что теряется не кнопка, а способность что-либо сделать по нажатию.

Запуск:
    python tools/check_surface_reachable.py
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

SURFACE = os.path.join(ROOT, "docs", "SURFACE-3.1.0.md")

fails = 0


def check(label, cond, detail=""):
    global fails
    if not cond:
        fails += 1
    print(("OK   " if cond else "FAIL "), label, detail)


#: Чем оболочка сделает то, что человек нажал. Ключ — начало строки действия
#: из инвентаря; значение — методы протокола, без которых не обойтись.
#:
#: Пустой список значит, что метод не нужен: действие целиком принадлежит
#: оболочке. Таких немного, и каждое объяснено.
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
    "Проверить микрофон": [],           # микрофон у оболочки (4.0-F09)
    "Проверить связь с моделью": ["settings.set"],
    "Проверить модели Piper": ["settings.get"],
    "Выбрать модель Vosk": ["settings.set"],
    "Добавить папку с программами": ["settings.set"],
    "Обновить список программ": ["apps.index"],
    "Забыть выученные соответствия": ["settings.set"],
    "Открыть папку журналов": [],       # папку открывает оболочка
    "Сбросить настройки": ["settings.set"],
    "Проверить обновления сейчас": [],  # обновления — блок U, своя дорога
    "Назначить любую из семи комбинаций": ["settings.set"],
    "Все настройки без исключения": ["settings.describe", "settings.get",
                                     "settings.set"],
    "Свернуть, развернуть, закрыть окно": [],   # окно принадлежит оболочке
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
