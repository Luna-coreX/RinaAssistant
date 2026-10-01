"""
C01, C02, C04: the tool model, argument validation, the permission
catalogue.

Checked without the application: the registry is part of the core and must
know nothing of Qt or of the settings.
"""
import os
import sys

ROOT = r"C:\DevStation\PCDev\DesktopApps\RinaAssistant"
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from core.permissions import (PERMISSIONS, RESERVED, UnknownPermission,
                              check_permission, dangerous)
from core.toolbox import ALL_TOOLS, default_registry
from core.tools import (InvalidArguments, Param, Tool, ToolRegistry,
                        UnknownTool, validate)

fails = 0


def check(label, cond, detail=""):
    global fails
    if not cond:
        fails += 1
    print(("OK   " if cond else "FAIL "), label, detail)


def raises(fn, exc):
    """The call is obliged to raise precisely this exception."""
    try:
        fn()
        return False
    except exc:
        return True


print("=== чистота ===")
check("Qt не загружен", "PySide6" not in sys.modules)
check("настройки не загружены", "core.settings_store" not in sys.modules)

print()
print("=== каталог разрешений (C04) ===")
check("все разрешения из плана заведены",
      {"process.launch", "system.media", "system.power", "network.external",
       "files.read", "files.write", "screen.read",
       "input.synthesize"} <= set(PERMISSIONS),
      f"| всего {len(PERMISSIONS)}")
check("опечатка отклоняется",
      raises(lambda: check_permission("system.powr"), UnknownPermission))
check("питание помечено опасным", dangerous({"system.power"}))
check("громкость опасной не считается", not dangerous({"system.media"}))

registry = default_registry()
used = set()
for tool in registry.all():
    used |= tool.permissions
check("зарезервированные разрешения никем не используются",
      not (RESERVED & used), f"| {sorted(RESERVED & used)}")
check("все использованные разрешения есть в каталоге",
      used <= set(PERMISSIONS))

print()
print("=== описания инструментов (C01) ===")
expected = {"launch_app", "list_apps", "set_volume", "media_control",
            "power_action", "take_screenshot", "create_reminder",
            "list_reminders", "cancel_reminder", "run_user_command",
            "dispatch_plugin_command", "calculate", "web_search",
            "ask_model"}
check("все инструменты из плана объявлены",
      expected <= set(registry.names()),
      f"| нет: {sorted(expected - set(registry.names()))}")
check("реестр непустой", len(registry) == len(ALL_TOOLS))

for tool in registry.all():
    if not tool.summary:
        check(f"{tool.name}: есть описание", False)
    if not tool.returns and tool.name != "silence":
        check(f"{tool.name}: описана форма результата", bool(tool.returns))

check("описание сериализуемо",
      isinstance(registry.describe(), list)
      and all(isinstance(d, dict) for d in registry.describe()))

print()
print("=== опасное обязано требовать подтверждения ===")
power = registry.get("power_action")
check("выключение требует подтверждения", power.confirm_required)
check("выключение помечено опасным", power.dangerous)
try:
    Tool(name="плохой", summary="…", permissions={"system.power"})
    check("нельзя объявить опасный инструмент без подтверждения", False)
except ValueError as e:
    check("нельзя объявить опасный инструмент без подтверждения", True,
          f"| {e}")

print()
print("=== идемпотентность расставлена осмысленно ===")
check("список программ идемпотентен", registry.get("list_apps").idempotent)
check("счёт идемпотентен", registry.get("calculate").idempotent)
check("запуск программы — нет", not registry.get("launch_app").idempotent)
check("создание напоминания — нет",
      not registry.get("create_reminder").idempotent)
check("отмена напоминаний идемпотентна",
      registry.get("cancel_reminder").idempotent)

print()
print("=== валидация аргументов (C02) ===")
ok = registry.validate("set_volume", {"action": "up"})
check("правильный вызов проходит", ok == {"action": "up"}, f"| {ok}")

try:
    registry.validate("set_volume", {"action": "louder"})
    check("значение вне списка отклонено", False)
except InvalidArguments as e:
    check("значение вне списка отклонено", True, f"| {e}")

try:
    registry.validate("set_volume", {})
    check("пропущенный обязательный отклонён", False)
except InvalidArguments as e:
    check("пропущенный обязательный отклонён", True, f"| {e}")

try:
    registry.validate("set_volume", {"action": "up", "volume": 50})
    check("лишний аргумент отклонён", False)
except InvalidArguments as e:
    check("лишний аргумент отклонён", True, f"| {e}")

try:
    registry.validate("create_reminder", {"kind": "timer", "seconds": "10"})
    check("строка вместо числа отклонена", False)
except InvalidArguments as e:
    check("строка вместо числа отклонена", True, f"| {e}")

try:
    registry.validate("create_reminder", {"kind": "timer", "seconds": True})
    check("логическое вместо числа отклонено", False)
except InvalidArguments as e:
    check("логическое вместо числа отклонено", True, f"| {e}")

try:
    registry.validate("create_reminder", {"kind": "timer", "seconds": 0})
    check("значение ниже минимума отклонено", False)
except InvalidArguments as e:
    check("значение ниже минимума отклонено", True, f"| {e}")

got = registry.validate("list_apps", {})
check("значение по умолчанию подставлено", got == {"limit": 20}, f"| {got}")

try:
    registry.validate("выдумка", {})
    check("неизвестный инструмент отклонён", False)
except UnknownTool as e:
    check("неизвестный инструмент отклонён", True, f"| {e.code}")

print()
print("=== сообщение годится для исправления с первой попытки ===")
try:
    registry.validate("set_volume", {"action": "louder"})
except InvalidArguments as e:
    text = str(e)
    check("названо имя инструмента", "set_volume" in text)
    check("назван аргумент", "action" in text)
    check("перечислены допустимые значения",
          "up" in text and "down" in text and "mute" in text, f"| {text}")
    check("есть машинные подробности",
          e.details.get("choices") == ["up", "down", "mute"],
          f"| {e.details}")

print()
print("=== реестр не молчит об ошибках объявления ===")
try:
    ToolRegistry([registry.get("calculate"), registry.get("calculate")])
    check("повторная регистрация отклонена", False)
except ValueError:
    check("повторная регистрация отклонена", True)

try:
    Tool(name="дубль", summary="…",
         params=(Param("x", "string", "…"), Param("x", "integer", "…")))
    check("повторяющиеся аргументы отклонены", False)
except ValueError:
    check("повторяющиеся аргументы отклонены", True)

try:
    Param("x", "дата", "…")
    check("неизвестный тип аргумента отклонён", False)
except ValueError:
    check("неизвестный тип аргумента отклонён", True)

print()
print("=== кто просит опасное ===")
power_tools = [t.name for t in registry.requiring("system.power")]
check("питание просит только power_action", power_tools == ["power_action"],
      f"| {power_tools}")

print()
print("=== всё, что умеет Рина, решено для конструктора (4.0b-K01) ===")
# The rule: everything Rina can do and that is safe to automate has a block
# in the command editor. Kept by making the decision part of declaring a
# tool — and by this check, so a tool cannot arrive without it.
from voice.user_commands import COMMAND_TYPES

kinds = {kind for kind, _title, _icon in COMMAND_TYPES}
#: What a person can type or pick. An object or a list has no field a
#: person could fill in sensibly, and a block asking for one is a block
#: nobody can use.
SIMPLE = {"string", "integer", "number", "boolean"}

undecided = [t.name for t in registry.all() if not t.automation]
check("у каждого инструмента есть решение", not undecided,
      f"| без решения: {undecided}")

for tool in registry.all():
    how = tool.automation
    if how == "no":
        check(f"{tool.name}: исключение названо с причиной",
              bool(tool.automation_note.strip()))
    elif how.startswith("kind:"):
        check(f"{tool.name}: вид шага «{how[5:]}» существует",
              how[5:] in kinds, f"| виды: {sorted(kinds)}")
    elif how in ("action", "query"):
        check(f"{tool.name}: у блока есть название", bool(tool.title.strip()))
        # A block runs inside a scenario that was confirmed as a whole, if
        # at all; a tool that asks on every call would fail there every
        # time. Such a tool belongs to a kind that confirms the command.
        check(f"{tool.name}: блок не требует подтверждения на каждый вызов",
              not tool.confirm_required)
        names = {p.name for p in tool.params}
        check(f"{tool.name}: поля блока — его аргументы",
              set(tool.asks) <= names, f"| {sorted(set(tool.asks) - names)}")
        check(f"{tool.name}: поля блока заполнимы руками",
              all(tool.param(a).type in SIMPLE for a in tool.asks
                  if tool.param(a)))
        # An argument the block does not ask for has to manage on its own,
        # or every step built from the block fails validation.
        unasked = [p.name for p in tool.params
                   if p.required and p.default is None
                   and p.name not in tool.asks]
        check(f"{tool.name}: обязательное без поля — с умолчанием",
              not unasked, f"| {unasked}")
    else:
        check(f"{tool.name}: решение из словаря", False, f"| {how!r}")

blocks = [t.name for t in registry.all() if t.automation in ("action", "query")]
for wanted in ("create_reminder", "list_reminders", "add_todo", "list_todo",
               "start_session", "finish_session", "set_focus", "tell_time"):
    check(f"«{wanted}» собирается в команду", wanted in blocks)

print()
print("ИТОГО ошибок:", fails)
sys.exit(1 if fails else 0)
