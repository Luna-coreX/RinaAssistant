"""
C07: the registry is the only path of execution. A check of an
architectural invariant.

C03 checked one file — the executor. Here the invariant is checked across
the whole core: side effects are performed only inside `core/toolrunner.py`,
and no other module of the core reaches them.

The check is over the syntax tree rather than by searching the text:
comments and documentation strings describe the code but are not code.
"""
import ast
import io
import os
import sys

ROOT = r"C:\DevStation\PCDev\DesktopApps\RinaAssistant"
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
os.chdir(ROOT)

fails = 0


def check(label, cond, detail=""):
    global fails
    if not cond:
        fails += 1
    print(("OK   " if cond else "FAIL "), label, detail)


# ---------------------------------------------------------------------------
# What counts as a side effect
# ---------------------------------------------------------------------------
FORBIDDEN_CALLS = {
    ("os", "startfile"),
    ("webbrowser", "open"),
    ("subprocess", "Popen"),
    ("subprocess", "run"),
    ("system_control", "run"),
    ("app_index", "launch"),
    ("llm", "ask"),
    ("websearch", "open_search"),
    ("websearch", "fallback_search"),
    ("user_commands", "execute"),
    ("execute", None),          # from voice.user_commands import execute
}

#: The core module allowed side effects. Exactly one.
ALLOWED = "toolrunner.py"

#: The second — and with a proviso that is checked below.
#:
#: `plugin_host.py` raises the plugins' processes (`4.0-H07`). The invariant
#: guards that **Rina's skills** do not go past the registry: launching a
#: program, opening the browser, asking the model. Loading a plugin is not a
#: skill but a way of loading one; that is decided by a person, by switching
#: the plugin on.
#:
#: A concession without a check is a way of blurring the invariant, so below
#: it is separately asserted: only our own launcher is started, without paths
#: from a person, without strings from a plugin and without the system's
#: shell.
LAUNCHER_ONLY = "plugin_host.py"


def calls_in(path):
    """Every call of the form `module.function` in a file."""
    tree = ast.parse(io.open(path, encoding="utf-8").read())
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            found.append(((func.value.id, func.attr), node.lineno))
        elif isinstance(func, ast.Name):
            found.append(((func.id, None), node.lineno))
    return found


print("=== инвариант: побочные эффекты только в одном модуле ===")
core_files = sorted(
    os.path.join("core", f) for f in os.listdir("core")
    if f.endswith(".py") and f != "__init__.py")

offenders = []
for path in core_files:
    if os.path.basename(path) in (ALLOWED, LAUNCHER_ONLY):
        continue
    for (owner, attr), line in calls_in(path):
        if (owner, attr) in FORBIDDEN_CALLS or (owner, None) in FORBIDDEN_CALLS:
            offenders.append(f"{path}:{line} {owner}.{attr}")

check("ядро не делает побочных эффектов мимо реестра", not offenders,
      f"| {offenders}")
print(f"     проверено файлов ядра: {len(core_files)}, "
      f"разрешён только {ALLOWED}")

# The proviso about plugin_host: only our own launcher is started.
host_source = io.open(os.path.join("core", LAUNCHER_ONLY),
                      encoding="utf-8").read()
host_tree = ast.parse(host_source)
spawns = [node for node in ast.walk(host_tree)
          if isinstance(node, ast.Call)
          and isinstance(node.func, ast.Attribute)
          and node.func.attr in ("Popen", "run", "call", "check_output")]
check("процесс плагина поднимается ровно в одном месте", len(spawns) == 1,
      f"| найдено {len(spawns)}")

launch_args = ast.dump(spawns[0]) if spawns else ""
check("запускается свой launcher, а не что попало",
      "attr='executable'" in launch_args and "host.py" in host_source,
      "| ни пути от человека, ни строки от плагина")
check("и без оболочки системы",
      "shell=True" not in host_source,
      "| shell=True превратил бы имя папки плагина в команду")

print()
print("=== инвариант: у каждого вызова назван инициатор ===")
# Without an initiator a journal entry is useless: "somebody shut the computer down".
tree = ast.parse(io.open("core/executor.py", encoding="utf-8").read())
missing = []
for node in ast.walk(tree):
    if not isinstance(node, ast.Call):
        continue
    func = node.func
    if not isinstance(func, ast.Attribute):
        continue
    is_run = (isinstance(func.value, ast.Name) and func.value.id == "self"
              and func.attr == "_run")
    is_call = (isinstance(func.value, ast.Attribute)
               and func.value.attr == "_tools" and func.attr == "call")
    if is_run or is_call:
        if not any(kw.arg == "source" for kw in node.keywords):
            missing.append(f"строка {node.lineno}")
check("каждый вызов инструмента называет инициатора", not missing,
      f"| {missing}")

print()
print("=== инвариант: объявленное и реализованное совпадают ===")
from core.toolbox import default_registry
from core.toolrunner import IMPLEMENTATIONS

registry = default_registry()
declared = set(registry.names())
check("нет объявленных без реализации", declared <= set(IMPLEMENTATIONS),
      f"| {sorted(declared - set(IMPLEMENTATIONS))}")
check("нет реализаций без объявления", set(IMPLEMENTATIONS) <= declared,
      f"| {sorted(set(IMPLEMENTATIONS) - declared)}")

print()
print("=== инвариант: опасное требует подтверждения ===")
from core.permissions import PERMISSIONS

unconfirmed = [t.name for t in registry.all()
               if t.dangerous and not t.confirm_required]
check("опасных без подтверждения нет", not unconfirmed, f"| {unconfirmed}")

unknown = [p for t in registry.all() for p in t.permissions
           if p not in PERMISSIONS]
check("все разрешения из каталога", not unknown, f"| {unknown}")

print()
print("=== инвариант: журнал пишет каждый вызов, включая отказы ===")
from core import logging_setup
logging_setup.setup()

from sandbox import neutralise
box = neutralise()

from core.audit import AuditLog
from core.settings_api import MemorySettings
from core.toolrunner import ToolContext, ToolRunner
from voice.reminders import ReminderStore
from voice.user_commands import UserCommandStore

settings = MemorySettings()
audit = AuditLog(path=":memory:")
# A stub shell: since 4.0-G01 it is what performs a system action.
runner = ToolRunner(ToolContext(
    settings=settings, reminders=ReminderStore(settings),
    commands=UserCommandStore(settings), emit=lambda n, **d: None,
    system_out=lambda action: (True, "")),
    audit=audit)

before = audit.count()
runner.call("set_volume", {"action": "up"}, source="voice")          # success
runner.call("power_action", {"action": "shutdown"}, source="voice")  # refused
runner.call("set_volume", {"action": "выдумка"}, source="typed")     # refused
runner.call("нет_такого", {}, source="typed")                        # refused
check("записаны все четыре вызова", audit.count() - before == 4,
      f"| {audit.count() - before}")

rows = audit.recent(4)
check("отказы записаны наравне с успехами",
      sum(1 for r in rows if not r["ok"]) == 3,
      f"| отказов {sum(1 for r in rows if not r['ok'])}")
check("у записей есть инициатор",
      all(r["source"] for r in rows),
      f"| {[r['source'] for r in rows]}")
check("у записей есть разрешения инструмента",
      any(r["permissions"] for r in rows))

print()
print("=== инвариант: журнал не превращается в стенограмму ===")

# The condition is set here rather than taken from the machine's settings:
# the invariant holds with text recording switched off, and the check is
# obliged to say so rather than inherit it. The first edition went red on a
# machine where `log_texts` is on — that is, it checked the operator rather
# than the program.
from core.settings_store import settings as real_settings

real_settings.load()
was_verbatim = bool(real_settings.get("log_texts", False))
real_settings._data["log_texts"] = False        # in memory only: we do not write

runner.call("web_search", {"query": "как приготовить борщ"}, source="typed")
row = audit.recent(1)[0]
check("свободный текст не записан дословно",
      row["args"]["query"] == "<20 симв.>", f"| {row['args']}")

runner.call("set_volume", {"action": "down"}, source="typed")
row = audit.recent(1)[0]
check("выбор из перечня записан дословно",
      row["args"]["action"] == "down", f"| {row['args']}")

runner.call("create_reminder",
            {"kind": "reminder", "seconds": 600, "text": "позвонить маме"},
            source="voice")
row = audit.recent(1)[0]
check("текст напоминания скрыт, а срок виден",
      row["args"]["text"].startswith("<") and row["args"]["seconds"] == 600,
      f"| {row['args']}")

# And the reverse: text recording switched on really does write them. A
# setting that changes nothing is the worst thing that can happen to a
# privacy setting: a person thinks they allowed it, and the journal is empty.
real_settings._data["log_texts"] = True
runner.call("web_search", {"query": "как приготовить борщ"}, source="typed")
verbatim_row = audit.recent(1)[0]
check("при включённой записи текст виден целиком",
      verbatim_row["args"].get("query") == "как приготовить борщ",
      f"| {verbatim_row['args']}")
real_settings._data["log_texts"] = was_verbatim

print()
print("ИТОГО ошибок:", fails)
sys.exit(1 if fails else 0)
