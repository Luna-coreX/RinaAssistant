"""
C03 and C05: the registry is the only path, confirmation is obligatory.

Two acceptance criteria, both checked literally:

    C03  the executor has not one path of execution around the registry
    C05  power_action without confirmation fails with an explicit error
"""
import ast
import io
import os
import sys

ROOT = r"C:\DevStation\PCDev\DesktopApps\RinaAssistant"
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
os.chdir(ROOT)

from core import logging_setup
logging_setup.setup()

from sandbox import neutralise
box = neutralise()

from core.confirmations import ConfirmationLedger, fingerprint
from core.settings_api import MemorySettings
from core.toolbox import default_registry
from core.toolrunner import ToolContext, ToolRunner

fails = 0


def check(label, cond, detail=""):
    global fails
    if not cond:
        fails += 1
    print(("OK   " if cond else "FAIL "), label, detail)


def make_runner():
    from voice.history import HistoryStore
    from voice.reminders import ReminderStore
    from voice.user_commands import UserCommandStore

    settings = MemorySettings()
    # The shell, which is not here: the core asks for a system action to be
    # performed (ADR 0009) rather than performing it itself. We record the
    # request and answer "it worked" — what is checked is that the
    # confirmation gates are in place, not that Windows can turn the volume
    # up.
    return ToolRunner(ToolContext(
        settings=settings,
        reminders=ReminderStore(settings),
        commands=UserCommandStore(settings),
        emit=lambda name, **data: None,
        system_out=lambda action: (DONE.append(action), (True, ""))[1],
    ))


#: What "the shell" did at the core's request.
DONE = []


print("=== C03: обходных путей нет ===")

# Side effects the executor has no right to perform itself.
#
# Checked over the syntax tree rather than by searching the text: the first
# edition caught a documentation string where exactly what the executor no
# longer does is described. Prose about code is not code.
FORBIDDEN_CALLS = {
    ("os", "startfile"),
    ("webbrowser", "open"),
    ("system_control", "run"),
    ("app_index", "launch"),
    ("llm", "ask"),
    ("user_commands", "execute"),
    ("subprocess", "Popen"),
    ("subprocess", "run"),
}
#: The stores' methods that change state. The executor is obliged to reach
#: them only through tools.
FORBIDDEN_METHODS = {"add", "clear_active", "bump_stat", "remove", "save"}

tree = ast.parse(io.open("core/executor.py", encoding="utf-8").read())
offenders = []
for node in ast.walk(tree):
    if not isinstance(node, ast.Call):
        continue
    func = node.func
    if not isinstance(func, ast.Attribute):
        continue
    owner = func.value
    if isinstance(owner, ast.Name) and (owner.id, func.attr) in FORBIDDEN_CALLS:
        offenders.append(f"{owner.id}.{func.attr} (строка {node.lineno})")
    # self._reminders.add(...) and the like
    if (isinstance(owner, ast.Attribute)
            and isinstance(owner.value, ast.Name)
            and owner.value.id == "self"
            and func.attr in FORBIDDEN_METHODS):
        offenders.append(f"self.{owner.attr}.{func.attr} "
                         f"(строка {node.lineno})")

check("исполнитель не делает побочных эффектов сам", not offenders,
      f"| {offenders}")

runner = make_runner()
declared = set(runner.registry.names())
from core.toolrunner import IMPLEMENTATIONS
check("у каждого объявленного есть реализация",
      declared <= set(IMPLEMENTATIONS),
      f"| нет: {sorted(declared - set(IMPLEMENTATIONS))}")
check("лишних реализаций нет",
      set(IMPLEMENTATIONS) <= declared,
      f"| лишние: {sorted(set(IMPLEMENTATIONS) - declared)}")

print()
print("=== C05: опасное без подтверждения не исполняется ===")
result = runner.call("power_action", {"action": "shutdown"})
check("вызов отклонён", not result.ok)
check("код ошибки говорит о причине",
      result.error_code == "confirmation.required", f"| {result.error_code}")
check("компьютер не выключался", not box.actions, f"| {box.actions}")

result = runner.call("power_action", {"action": "shutdown"},
                     confirmation_id="выдуманный")
check("поддельное подтверждение отклонено",
      not result.ok and result.error_code == "confirmation.invalid",
      f"| {result.error_code}")

print()
print("=== подтверждение работает ровно один раз ===")
confirmation = runner.request_confirmation(
    "power_action", {"action": "shutdown"}, preview="Точно выключить?")
result = runner.call("power_action", {"action": "shutdown"},
                     confirmation_id=confirmation.id)
check("с подтверждением выполняется", result.ok, f"| {result.message}")
# We look at the request to the shell rather than at the sandbox: the core no
# longer touches the machine itself, and `box.actions` is now empty in
# substance (ADR 0009).
check("действие произошло", DONE == ["shutdown"], f"| {DONE}")

box.actions.clear()
result = runner.call("power_action", {"action": "shutdown"},
                     confirmation_id=confirmation.id)
check("повторное предъявление отклонено",
      not result.ok and result.error_code == "confirmation.invalid",
      f"| {result.error_code}")
# There was exactly one request to the shell: the second presentation was
# rejected before the tool reached the system layer.
check("второй раз не выключилось", DONE == ["shutdown"], f"| {DONE}")

print()
print("=== подтверждение привязано к аргументам ===")
confirmation = runner.request_confirmation("power_action", {"action": "sleep"})
box.actions.clear()
result = runner.call("power_action", {"action": "shutdown"},
                     confirmation_id=confirmation.id)
check("согласие на сон не годится для выключения",
      not result.ok and result.error_code == "confirmation.invalid",
      f"| {result.error_code}")
check("компьютер не выключился", not box.actions, f"| {box.actions}")

result = runner.call("power_action", {"action": "sleep"},
                     confirmation_id=confirmation.id)
check("для своего действия годится", result.ok, f"| {result.message}")

print()
print("=== просроченное подтверждение ===")
import time

ledger = ConfirmationLedger(ttl=0.01)
confirmation = ledger.issue("power_action", {"action": "shutdown"})
time.sleep(0.05)
try:
    ledger.redeem(confirmation.id, "power_action", {"action": "shutdown"})
    check("просроченное отклонено", False)
except Exception as e:
    check("просроченное отклонено", getattr(e, "code", "") ==
          "confirmation.expired", f"| {getattr(e, 'code', e)}")

print()
print("=== ворота стоят в правильном порядке ===")
# A wrong argument is rebuffed BEFORE confirmation is asked for: a person
# must not be asked about a call that will not take place anyway.
result = runner.call("power_action", {"action": "выдумка"})
check("аргументы проверяются раньше подтверждения",
      result.error_code == "tool.invalid_arguments", f"| {result.error_code}")

result = runner.call("выдуманный_инструмент", {})
check("неизвестный инструмент отбивается первым",
      result.error_code == "tool.unknown", f"| {result.error_code}")

print()
print("=== безопасные инструменты подтверждения не требуют ===")
result = runner.call("calculate", {"expression": "посчитай 15*12"})
check("счёт работает без подтверждения",
      result.ok and "180" in result.message, f"| {result.message}")
result = runner.call("set_volume", {"action": "up"})
check("громкость работает без подтверждения", result.ok, f"| {result.message}")

print()
print("ИТОГО ошибок:", fails)
sys.exit(1 if fails else 0)
