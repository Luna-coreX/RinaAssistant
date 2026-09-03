"""
C03 и C05: реестр — единственный путь, подтверждение обязательно.

Два критерия приёмки, оба проверяются буквально:

    C03  исполнитель не имеет ни одного пути исполнения в обход реестра
    C05  power_action без подтверждения падает с явной ошибкой
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
    # Оболочка, которой здесь нет: ядро просит сделать системное действие
    # (ADR 0009), а не делает само. Записываем просьбу и отвечаем
    # «получилось» — проверяется, что ворота подтверждений на месте, а не
    # что Windows умеет прибавлять громкость.
    return ToolRunner(ToolContext(
        settings=settings,
        reminders=ReminderStore(settings),
        commands=UserCommandStore(settings),
        emit=lambda name, **data: None,
        system_out=lambda action: (DONE.append(action), (True, ""))[1],
    ))


#: Что «оболочка» сделала по просьбе ядра.
DONE = []


print("=== C03: обходных путей нет ===")

# Побочные эффекты, которые исполнитель не имеет права делать сам.
#
# Проверяется по синтаксическому дереву, а не поиском по тексту: первая
# редакция ловила строку документации, где как раз описано, чего исполнитель
# больше не делает. Проза о коде — не код.
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
#: Методы хранилищ, меняющие состояние. Исполнитель обязан ходить в них
#: только через инструменты.
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
    # self._reminders.add(...) и подобное
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
# Смотрим на просьбу к оболочке, а не на песочницу: ядро больше не
# трогает машину само, и `box.actions` теперь пуст по существу (ADR 0009).
check("действие произошло", DONE == ["shutdown"], f"| {DONE}")

box.actions.clear()
result = runner.call("power_action", {"action": "shutdown"},
                     confirmation_id=confirmation.id)
check("повторное предъявление отклонено",
      not result.ok and result.error_code == "confirmation.invalid",
      f"| {result.error_code}")
# Просьба к оболочке была ровно одна: второе предъявление отклонили до
# того, как инструмент дошёл до системного слоя.
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
# Неверный аргумент отбивается ДО того, как спросят подтверждение:
# человека не должны спрашивать про вызов, который всё равно не состоится.
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
