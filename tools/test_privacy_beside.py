# -*- coding: utf-8 -*-
"""
What is kept beside the store is on the privacy page and goes with
«забыть всё».

Found by the audit of 2026-10-07 (H-4, M-1). The page walked the keys of
the settings store and nothing else. On the disk, and nowhere on the page:
the journals — the security one with every program launched, its path and
time; the call journal; whole copies of the history and commands made
before a migration; what the shell keeps. A person who pressed «забыть всё»
kept a copy of their conversation in `backup-v*`. And telemetry forgotten
from the page came straight back: the page forgot its own copy while the
engine wrote the old one, identifier and all, on the next command.

Checked here in an isolated data folder, with the shell substituted:

- every one of those is a group of the page, with what it holds;
- each can be forgotten, and «забыть всё» takes them all;
- after it, nothing with content is left in the data folder except the
  store itself at its defaults and the downloaded models;
- forgotten telemetry stays forgotten: a new identifier, not the old one.

To run:
    python tools/test_privacy_beside.py
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

from console import use_utf8
from sandbox import isolate_storage

use_utf8()
isolate_storage()

from core import privacy
from core.audit import AuditLog
from core.logging_setup import logs_dir, security_log, setup
from core.settings_store import settings as store
from core.telemetry import Telemetry

fails = 0


def check(label, cond, detail=""):
    global fails
    if not cond:
        fails += 1
    print(("OK   " if cond else "FAIL "), label, detail)


def group(groups, name):
    return next((one for one in groups if one["id"] == name), None)


class Shell:
    """The shell's `kept.*`, as it answers them."""

    def __init__(self):
        self.consents = {r"c:\tools\old-thing.exe": 1700000000,
                         r"c:\games\launcher.exe": 1710000000}
        self.index = 312

    def __call__(self, method, payload):
        if method == "kept.list":
            return {"consents": [{"path": p, "at": at}
                                 for p, at in self.consents.items()],
                    "index": self.index}
        gone = 0
        if "consents" in payload:
            wanted = payload["consents"]
            for path in list(self.consents):
                if wanted is None or path in wanted:
                    del self.consents[path]
                    gone += 1
        if payload.get("index"):
            gone += self.index
            self.index = 0
        return {"forgotten": gone}


# --- a data folder with everything a person's use leaves behind ------------
setup(force=True)
folder = store._dir
store.set("history", [{"role": "user", "text": "секретный разговор"}])
store.save()
for name in ("backup-v2", "backup-before-cleanup-2026-09-29"):
    os.makedirs(os.path.join(folder, name), exist_ok=True)
    with open(os.path.join(folder, name, "history.json"), "w",
              encoding="utf-8") as f:
        json.dump([{"text": "секретный разговор"}], f, ensure_ascii=False)
security_log().info("launch app=old-thing.exe path=C:\\tools\\old-thing.exe")
with open(os.path.join(logs_dir(), "shell.log"), "w", encoding="utf-8") as f:
    f.write("2026-10-07 INFO shell started\n")

audit = AuditLog(os.path.join(folder, "audit.db"))
store.set("telemetry", True)
telemetry = Telemetry(store)
telemetry.intent("calc")
telemetry.flush()
first_id = telemetry.report()["install"] if telemetry.report() else ""

shell = Shell()
local = privacy.Local(folder=folder, audit=audit, telemetry=telemetry,
                      shell=shell)

# ---------------------------------------------------------------------------
print("=== на странице — и то, что лежит рядом с хранилищем ===")
groups = privacy.inventory(store, None, local)
journals = group(groups, "journals")
check("журналы — группа, по файлам",
      journals and {"rina.log", "security.log", "shell.log"}
      <= {i["id"] for i in journals["items"]}, f"| {journals}")
backups = group(groups, "backups")
check("резервные копии видны, все, а не только backup-v*",
      backups and {"backup-v2", "backup-before-cleanup-2026-09-29"}
      <= {i["id"] for i in backups["items"]}, f"| {backups}")
consents = group(groups, "consents")
check("согласия на запуск — из оболочки, с путями",
      consents and consents["count"] == 2, f"| {consents}")
index = group(groups, "program_index")
check("список программ — сколько", index and "312" in index["items"][0]["what"],
      f"| {index}")
check("журнал вызовов — группа", group(groups, "calls") is not None)
without = {g["id"] for g in privacy.inventory(store, None,
                                               privacy.Local(folder=folder))}
check("без оболочки её групп нет — «ничего не хранится» было бы неправдой",
      "consents" not in without and "program_index" not in without)

# ---------------------------------------------------------------------------
print()
print("=== забытая телеметрия не возвращается (M-1) ===")
privacy.forget(store, "telemetry", None, None, local)
telemetry.intent("calc")
telemetry.flush()
again = telemetry.report() or {}
check("после «забыть» — новый идентификатор, а не прежний",
      first_id and again.get("install") and again["install"] != first_id,
      f"| был {first_id}, стал {again.get('install')}")

# ---------------------------------------------------------------------------
print()
print("=== по одному ===")
gone = privacy.forget(store, "consents", [r"c:\tools\old-thing.exe"], None, local)
check("одно согласие забыто, другое осталось",
      gone == 1 and list(shell.consents) == [r"c:\games\launcher.exe"])
gone = privacy.forget(store, "backups", ["backup-v2"], None, local)
check("одна копия удалена, другая на месте",
      gone == 1 and not os.path.exists(os.path.join(folder, "backup-v2"))
      and os.path.exists(os.path.join(folder,
                                      "backup-before-cleanup-2026-09-29")))

# ---------------------------------------------------------------------------
print()
print("=== «забыть всё» — всё ===")
privacy.forget_everything(store, None, local)
groups = privacy.inventory(store, None, local)
left = {g["id"]: g["count"] for g in groups if g["count"]}
# The journals are written to on the way — forgetting is itself an event —
# so what may remain there is the line about it, not what was before.
leftover_logs = []
for name in os.listdir(logs_dir()):
    with open(os.path.join(logs_dir(), name), encoding="utf-8",
              errors="replace") as f:
        if "old-thing" in f.read() or "shell started" in f.read():
            leftover_logs.append(name)
left.pop("journals", None)
# Telemetry is still switched on — forgetting the records is not switching
# it off, which is the person's choice — so a fresh, empty counter with a
# new identifier is honestly there. What must be gone is the old ones.
shown = json.dumps(group(groups, "telemetry"), ensure_ascii=False)
check("прежних идентификаторов телеметрии на странице нет",
      first_id not in shown and again["install"] not in shown)
left.pop("telemetry", None)
check("на странице не осталось ничего", left == {}, f"| {left}")
check("в журналах — ни строчки из прежнего", leftover_logs == [],
      f"| {leftover_logs}")
check("оболочка забыла согласия и список программ",
      shell.consents == {} and shell.index == 0)

with_content = []
for top, dirs, files in os.walk(folder):
    for name in files:
        path = os.path.join(top, name)
        rel = os.path.relpath(path, folder)
        if rel.startswith("logs") or rel.startswith("models"):
            continue
        with open(path, "rb") as f:
            body = f.read()
        if "секретный".encode("utf-8") in body:
            with_content.append(rel)
check("в каталоге данных не осталось ни одной копии сказанного",
      with_content == [], f"| {with_content}")
check("и папок с копиями — тоже",
      not any(n.startswith("backup-") for n in os.listdir(folder)),
      f"| {sorted(os.listdir(folder))}")

print()
print("ИТОГО ошибок:", fails)
sys.exit(1 if fails else 0)
