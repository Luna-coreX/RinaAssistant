# -*- coding: utf-8 -*-
"""
Сверка контракта протокола со снимком: что изменилось и можно ли так.

Задача плана 4.0-D17. Правила совместимости записаны в §4 спецификации
словами, и словами они и остались бы: человек, добавляющий поле, читает не
спецификацию, а соседнюю строчку кода. Здесь они становятся проверкой.

Снимок — `docs/protocol/contract-v1.json`: методы, события с полями, коды
ошибок, возможности, виды потоков. Он не документация, а точка отсчёта:
сверка отвечает не «правильно ли устроен протокол», а «что изменилось с
прошлого раза и требует ли это новой версии».

Разрешено без смены версии протокола:

    добавить метод, событие, код ошибки, возможность, вид потока
    добавить **необязательное** поле события
    добавить значение в перечисление

Требует новой версии:

    удалить или переименовать что угодно из перечисленного
    удалить поле, изменить его тип, сделать необязательное обязательным
    убрать значение из перечисления
    изменить категорию или повторяемость кода ошибки
    перенести метод в другую возможность

Про категорию и повторяемость стоит пояснить: по ним ветвится оболочка.
Код, вчера бывший `user` и неповторяемым, а сегодня `system` и повторяемым,
меняет поведение чужой программы, ничего не сломав синтаксически, — то есть
худшим из возможных способов.

Запуск:
    python tools/check_contract.py            сверить
    python tools/check_contract.py --update   переписать снимок
"""

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

SNAPSHOT = os.path.join(ROOT, "docs", "protocol", "contract-v1.json")


def current() -> dict:
    """Контракт, каким его описывает код прямо сейчас."""
    from core.confirmations import SCOPES
    from core.wire.data import KINDS
    from core.wire.errors import CATALOGUE
    from core.wire.events import EVENTS
    from core.wire.handshake import BASE_METHODS, CAPABILITIES

    methods = {name: None for name in BASE_METHODS}
    for cap in CAPABILITIES.values():
        for name in cap.methods:
            methods[name] = cap.name

    events = {}
    for name, spec in EVENTS.items():
        events[name] = {
            f.name: {
                "type": f.type,
                "required": f.required,
                "choices": sorted(f.choices),
                "low": f.low,
                "high": f.high,
            }
            for f in spec.fields
        }

    return {
        "protocol_version": 1,
        "methods": methods,
        "events": events,
        "errors": {code: {"category": s.category, "retryable": s.retryable}
                   for code, s in CATALOGUE.items()},
        "capabilities": {c.name: {"side": c.side, "methods": sorted(c.methods)}
                         for c in CAPABILITIES.values()},
        "stream_kinds": dict(KINDS),
        "scopes": sorted(SCOPES),
    }


def diff(old: dict, new: dict) -> tuple[list[str], list[str]]:
    """Вернуть (разрешённые изменения, ломающие)."""
    added, broken = [], []

    def compare_set(kind, old_names, new_names):
        for name in sorted(set(new_names) - set(old_names)):
            added.append(f"добавлен(о) {kind}: {name}")
        for name in sorted(set(old_names) - set(new_names)):
            broken.append(f"удалён(о) {kind}: {name}")

    compare_set("метод", old["methods"], new["methods"])
    compare_set("событие", old["events"], new["events"])
    compare_set("код ошибки", old["errors"], new["errors"])
    compare_set("возможность", old["capabilities"], new["capabilities"])
    compare_set("вид потока", old["stream_kinds"], new["stream_kinds"])
    compare_set("область разрешения", old["scopes"], new["scopes"])

    # метод переехал в другую возможность — меняется, когда его можно звать
    for name in sorted(set(old["methods"]) & set(new["methods"])):
        if old["methods"][name] != new["methods"][name]:
            broken.append(
                f"метод {name} сменил возможность: "
                f"{old['methods'][name]} -> {new['methods'][name]}")

    # ошибка сменила смысл: по категории и повторяемости ветвится оболочка
    for code in sorted(set(old["errors"]) & set(new["errors"])):
        was, now = old["errors"][code], new["errors"][code]
        for field in ("category", "retryable"):
            if was[field] != now[field]:
                broken.append(f"ошибка {code}: {field} "
                              f"{was[field]!r} -> {now[field]!r}")

    # поля событий
    for name in sorted(set(old["events"]) & set(new["events"])):
        was, now = old["events"][name], new["events"][name]
        for field in sorted(set(now) - set(was)):
            if now[field]["required"]:
                broken.append(
                    f"событие {name}: добавлено ОБЯЗАТЕЛЬНОЕ поле {field}")
            else:
                added.append(
                    f"событие {name}: добавлено необязательное поле {field}")
        for field in sorted(set(was) - set(now)):
            broken.append(f"событие {name}: удалено поле {field}")
        for field in sorted(set(was) & set(now)):
            a, b = was[field], now[field]
            if a["type"] != b["type"]:
                broken.append(f"событие {name}, поле {field}: тип "
                              f"{a['type']} -> {b['type']}")
            if not a["required"] and b["required"]:
                broken.append(f"событие {name}, поле {field}: "
                              "необязательное стало обязательным")
            lost = set(a["choices"]) - set(b["choices"])
            gained = set(b["choices"]) - set(a["choices"])
            if lost:
                broken.append(f"событие {name}, поле {field}: убраны значения "
                              f"{sorted(lost)}")
            if gained:
                added.append(f"событие {name}, поле {field}: добавлены "
                             f"значения {sorted(gained)}")

    if old.get("protocol_version") != new.get("protocol_version"):
        added.append(f"версия протокола {old.get('protocol_version')} -> "
                     f"{new.get('protocol_version')}")
    return added, broken


def main(argv) -> int:
    contract = current()

    if "--update" in argv:
        with open(SNAPSHOT, "w", encoding="utf-8") as f:
            json.dump(contract, f, ensure_ascii=False, indent=2,
                      sort_keys=True)
            f.write("\n")
        print(f"снимок переписан: {os.path.relpath(SNAPSHOT, ROOT)}")
        print(f"  методов {len(contract['methods'])}, "
              f"событий {len(contract['events'])}, "
              f"кодов ошибок {len(contract['errors'])}")
        return 0

    if not os.path.isfile(SNAPSHOT):
        print("снимка нет; создайте его: python tools/check_contract.py --update")
        return 1

    with open(SNAPSHOT, encoding="utf-8") as f:
        old = json.load(f)

    added, broken = diff(old, contract)

    print("=== D17: изменения контракта против снимка ===")
    if not added and not broken:
        print("  изменений нет")
    for line in added:
        print("  можно  ", line)
    for line in broken:
        print("  ЛОМАЕТ ", line)

    print()
    if broken:
        print(f"Ломающих изменений: {len(broken)}.")
        print("Такое требует новой версии протокола (§4). Если это и есть")
        print("намерение — поднимите версию и перепишите снимок:")
        print("    python tools/check_contract.py --update")
        return 1

    print(f"Совместимо. Добавлений: {len(added)}.")
    if added:
        print("Снимок стоит обновить тем же коммитом, что и добавления.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
