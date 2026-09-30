# -*- coding: utf-8 -*-
"""
Comparing the protocol's contract with a snapshot: what changed and whether
that is allowed.

Plan item 4.0-D17. The compatibility rules are written down in §4 of the
specification in words, and in words they would have stayed: a person adding
a field reads not the specification but the neighbouring line of code. Here
they become a check.

The snapshot is `docs/protocol/contract-v1.json`: the methods, the events
with their fields, the error codes, the capabilities, the kinds of stream.
It is not documentation but a point of reference: the comparison answers not
"is the protocol built rightly" but "what has changed since last time and
does it require a new version".

Allowed without changing the protocol's version:

    adding a method, an event, an error code, a capability, a kind of stream
    adding an **optional** field to an event
    adding a value to an enumeration

Requires a new version:

    deleting or renaming any of the above
    deleting a field, changing its type, making an optional one required
    removing a value from an enumeration
    changing an error code's category or retryability
    moving a method into another capability

The category and retryability are worth explaining: the shell branches on
them. A code that was `user` and non-retryable yesterday and is `system` and
retryable today changes another program's behaviour without breaking
anything syntactically — that is, in the worst possible way.

To run:
    python tools/check_contract.py            compare
    python tools/check_contract.py --update   rewrite the snapshot
"""

import json
import os
import sys

from console import use_utf8

use_utf8()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

SNAPSHOT = os.path.join(ROOT, "docs", "protocol", "contract-v1.json")


def current() -> dict:
    """The contract as the code describes it right now."""
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
    """Return (the permitted changes, the breaking ones)."""
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

    # a method moved into another capability — this changes when it may be called
    for name in sorted(set(old["methods"]) & set(new["methods"])):
        if old["methods"][name] != new["methods"][name]:
            broken.append(
                f"метод {name} сменил возможность: "
                f"{old['methods'][name]} -> {new['methods'][name]}")

    # an error changed its meaning: the shell branches on the category and retryability
    for code in sorted(set(old["errors"]) & set(new["errors"])):
        was, now = old["errors"][code], new["errors"][code]
        for field in ("category", "retryable"):
            if was[field] != now[field]:
                broken.append(f"ошибка {code}: {field} "
                              f"{was[field]!r} -> {now[field]!r}")

    # the events' fields
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
