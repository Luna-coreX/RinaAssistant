"""
C07: реестр — единственный путь исполнения. Проверка архитектурного инварианта.

C03 проверял один файл — исполнитель. Здесь инвариант проверяется по всему
ядру: побочные эффекты выполняются только внутри `core/toolrunner.py`, и
никакой другой модуль ядра до них не дотягивается.

Проверка по синтаксическому дереву, а не поиском по тексту: комментарии и
строки документации описывают код, но кодом не являются.
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
# Что считается побочным эффектом
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

#: Модуль ядра, которому побочные эффекты разрешены. Ровно один.
ALLOWED = "toolrunner.py"

#: Второй — и с оговоркой, которая проверяется ниже.
#:
#: `plugin_host.py` поднимает процессы плагинов (`4.0-H07`). Инвариант
#: сторожит, чтобы **умения Рины** не проходили мимо реестра: запуск
#: программы, открытие браузера, вопрос модели. Загрузка плагина — не
#: умение, а способ его загрузить; решает это человек, включая плагин.
#:
#: Послабление без проверки — способ размыть инвариант, поэтому ниже
#: отдельно утверждается: запускается только наш собственный launcher, без
#: путей от человека, без строк от плагина и без оболочки системы.
LAUNCHER_ONLY = "plugin_host.py"


def calls_in(path):
    """Все вызовы вида `модуль.функция` в файле."""
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

# Оговорка про plugin_host: запускается только свой launcher.
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
# Без инициатора запись в журнале бесполезна: «кто-то выключил компьютер».
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
# Оболочка-заглушка: системное действие с 4.0-G01 делает она.
runner = ToolRunner(ToolContext(
    settings=settings, reminders=ReminderStore(settings),
    commands=UserCommandStore(settings), emit=lambda n, **d: None,
    system_out=lambda action: (True, "")),
    audit=audit)

before = audit.count()
runner.call("set_volume", {"action": "up"}, source="voice")          # успех
runner.call("power_action", {"action": "shutdown"}, source="voice")  # отказ
runner.call("set_volume", {"action": "выдумка"}, source="typed")     # отказ
runner.call("нет_такого", {}, source="typed")                        # отказ
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

print()
print("ИТОГО ошибок:", fails)
sys.exit(1 if fails else 0)
