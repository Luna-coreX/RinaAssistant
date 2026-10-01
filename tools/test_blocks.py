# -*- coding: utf-8 -*-
"""
4.0b-K01: everything Rina can do is in the command editor.

A person's own command reaches Rina's abilities through blocks taken from
the tool registry, and the checks here run a real core, in the sandbox:

- a block goes through the registry, with `command` as the initiator in
  the journal, and a tool that is not a block is refused when it runs —
  whatever the card says and however it arrived;
- a scenario speaks as it runs. Until K01 nothing inside a sequence was
  said: the steps' words were computed and thrown away, and «Доброе утро»
  built of "say" steps was silent;
- a command of one block answers with the block's own answer;
- cards written before the blocks keep working.

To run:
    python tools/test_blocks.py
"""
import os
import sys
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

from console import use_utf8
from sandbox import neutralise

use_utf8()
box = neutralise()

from core.engine import RinaEngine
from core import data_transfer
from voice import user_commands

fails = 0


def check(label, cond, detail=""):
    global fails
    if not cond:
        fails += 1
    print(("OK   " if cond else "FAIL "), label, detail)


engine = RinaEngine()
said = []
# Through the attribute the core's own lambdas read, so the scenario's
# voice is the one being listened to — not a second one beside it.
engine.say = lambda text, sound="response": said.append(text)


def run(command):
    """
    Save a card, fire it the way a phrase does, and wait for its thread.

    The thread itself is waited for, not a fixed second and a half: under
    the full regression a scenario's third step had not run yet when the
    sleep ran out, and the check went red on a machine that was merely
    busy. A wait on the clock measures the machine; a join measures the
    scenario.
    """
    said.clear()
    engine._cmd_store.add(dict(command))
    before = set(threading.enumerate())
    result = engine._tools.call("run_user_command",
                                {"command_id": command["id"]},
                                source="typed")
    for started in set(threading.enumerate()) - before:
        started.join(timeout=30)
    return result


def step(kind, **fields):
    return dict({"type": kind}, **fields)


# ---------------------------------------------------------------------------
print("=== сценарий говорит по ходу ===")

result = run({
    "id": "k01_morning", "enabled": True, "type": "sequence",
    "triggers": ["доброе утро проверка"], "response": "",
    "steps": [
        step("speak", target="Доброе утро."),
        step("tool", tool="tell_time", args={"what": "weekday"}),
        step("tool", tool="add_todo", args={"text": "купить хлеб"}),
        step("tool", tool="list_todo", args={}),
        step("speak", target="А теперь — кофе."),
    ]})
check("последовательность не говорит «Выполняю…», если шаги говорят сами",
      result.ok and not result.message, f"| {result.message!r}")
check("шаги «Озвучить» звучат, и по порядку",
      said[:1] == ["Доброе утро."] and said[-1:] == ["А теперь — кофе."],
      f"| {said}")
check("ответ блока-вопроса звучит",
      any(line.startswith("Сегодня ") for line in said), f"| {said}")
check("блок-действие сценарий не комментирует",
      not any(line.startswith("Записала") for line in said), f"| {said}")
check("и всё равно выполнено",
      any("купить хлеб" == i["text"] for i in engine._todo.all()))

recent = engine._tools.audit.recent(10)
blocks_called = [(r["tool"], r["source"]) for r in recent
                 if r["tool"] in ("tell_time", "add_todo", "list_todo")]
check("блоки идут через реестр, инициатор — команда",
      len(blocks_called) == 3
      and all(source == "command" for _t, source in blocks_called),
      f"| {blocks_called}")

# The command's own answer was ignored for a sequence until K01.
run({"id": "k01_answer", "enabled": True, "type": "sequence",
     "triggers": ["окружение проверка"],
     "response": "Запускаю рабочее окружение.",
     "steps": [step("pause", target="0")]})
check("ответ последовательности звучит первым",
      said[:1] == ["Запускаю рабочее окружение."], f"| {said}")

result = run({"id": "k01_quiet", "enabled": True, "type": "sequence",
              "triggers": ["тихо проверка"], "response": "",
              "steps": [step("pause", target="0")]})
check("молчаливая последовательность говорит хотя бы, что выполняется",
      said == ["Выполняю последовательность."], f"| {said}")

# ---------------------------------------------------------------------------
print()
print("=== «Узнать» и подстановка: одна реплика (4.0b-K02) ===")

engine._settings.set("user_name", "Luna")
run({"id": "k02_morning", "enabled": True, "type": "sequence",
     "triggers": ["доброе утро одной фразой"], "response": "",
     "steps": [
         step("get", tool="user_name", args={}, name="имя"),
         step("get", tool="tell_time", args={"what": "weekday"},
              name="день недели"),
         step("speak", target="Доброе утро, {имя}) Сегодня {день недели}. "
                              "А теперь — кофе."),
     ]})
check("сценарий звучит одной репликой", len(said) == 1, f"| {said}")
check("значения встали на свои места",
      said[:1] and said[0].startswith("Доброе утро, Luna) Сегодня ")
      and "{" not in said[0], f"| {said}")
check("день — словом, а не фразой «Сегодня четверг.»",
      said[:1] and "Сегодня Сегодня" not in said[0], f"| {said}")

run({"id": "k02_closing", "enabled": True, "type": "sequence",
     "triggers": ["ответ в конце"], "response": "Готово, {имя}.",
     "steps": [step("get", tool="user_name", args={}, name="имя")]})
check("ответ с подстановкой звучит в конце, когда значение уже узнано",
      said == ["Готово, Luna."], f"| {said}")

run({"id": "k02_unknown", "enabled": True, "type": "sequence",
     "triggers": ["неизвестное"], "response": "",
     "steps": [step("speak", target="Погода: {погода}.")]})
check("неизвестное значение не пропадает молча",
      said == ["Погода: {погода}."], f"| {said}")

run({"id": "k02_action", "enabled": True, "type": "sequence",
     "triggers": ["узнать действием"], "response": "",
     "steps": [step("get", tool="add_todo", args={"text": "тайком"},
                    name="x"),
               step("speak", target="{x}")]})
check("«Узнать» не вызывает действие",
      not any(i["text"] == "тайком" for i in engine._todo.all()))

engine._settings.set("user_name", "")
named = engine._tools.call_block("user_name", {})
check("без имени в настройках — пустое значение, а не сбой",
      named.ok and named.value == "", f"| {named.value!r}")

# ---------------------------------------------------------------------------
print()
print("=== напоминание из блока ===")
made = engine._tools.call_block("create_reminder",
                                {"kind": "timer", "minutes": 10})
check("минуты — минуты", made.ok and "10 мин" in made.message,
      f"| {made.message}")
empty = engine._tools.call_block("create_reminder", {"kind": "timer"})
check("без срока напоминание не ставится, а не срабатывает сразу",
      not empty.ok, f"| {empty.message}")
engine._tools.call("cancel_reminder", {})

# ---------------------------------------------------------------------------
print()
print("=== яркость (4.0b-K04) ===")
asked_shell = []


def shell_with(answer):
    """A shell that records what it was asked and answers as told."""
    def do(action, **extra):
        asked_shell.append((action, extra))
        return answer
    return do


engine.system_out = shell_with((True, "45"))
done = engine._tools.call_block("set_brightness", {"how": "set", "level": 45})
check("уровень уходит оболочке числом рядом с действием",
      done.ok and asked_shell[-1] == ("brightness_set", {"level": 45}),
      f"| {asked_shell[-1:]}")
check("и сказан словами", done.message == "Яркость 45%.", f"| {done.message}")

engine._tools.call_block("set_brightness", {"how": "down"})
check("«темнее» — шаг, без уровня",
      asked_shell[-1] == ("brightness_down", {}), f"| {asked_shell[-1:]}")

engine.system_out = shell_with((False, "unsupported"))
refused = engine._tools.call_block("set_brightness", {"how": "up"})
check("экран, который не слушается, назван, а не «готово»",
      not refused.ok and "DDC/CI" in refused.message, f"| {refused.message}")

missing = engine._tools.call_block("set_brightness", {"how": "set"})
check("«поставить на уровень» без уровня — отказ",
      not missing.ok and missing.error_code == "tool.invalid_arguments")
engine.system_out = None

# ---------------------------------------------------------------------------
print()
print("=== что нельзя — нельзя, откуда бы ни пришла карточка ===")

run({"id": "k01_forbidden", "enabled": True, "type": "sequence",
     "triggers": ["запрет проверка"], "response": "",
     "steps": [step("tool", tool="try_user_command", args={}),
               step("tool", tool="power_action",
                    args={"action": "shutdown"}),
               step("tool", tool="no_such_tool", args={})]})
refused = [r for r in engine._tools.audit.recent(10)
           if r["tool"] in ("try_user_command", "power_action",
                            "no_such_tool")]
check("инструмент не из блоков не вызывается",
      refused and all(not r["ok"] for r in refused), f"| {refused}")
check("отказ записан в журнал, с командой как инициатором",
      len(refused) == 3 and all(r["source"] == "command" for r in refused),
      f"| {[(r['tool'], r['source']) for r in refused]}")
check("компьютер при этом никто не выключал", not box.actions,
      f"| {box.actions}")
check("неудача блока сказана вслух",
      "Команда не может этого сделать." in said, f"| {said}")

# ---------------------------------------------------------------------------
print()
print("=== команда из одного блока ===")

result = run({"id": "k01_single", "enabled": True, "type": "tool",
              "tool": "add_todo", "args": {"text": "позвонить"},
              "triggers": ["запиши звонок"], "response": ""})
check("отвечает ответом блока",
      result.ok and "позвонить" in result.message, f"| {result.message!r}")

result = run({"id": "k01_single_told", "enabled": True, "type": "tool",
              "tool": "set_focus", "args": {"on": True},
              "triggers": ["фокус проверка"], "response": "Тишина."})
check("а свой ответ карточки важнее",
      result.ok and result.message == "Тишина.", f"| {result.message!r}")
engine._tools.call("set_focus", {"on": False})

result = run({"id": "k01_single_bad", "enabled": True, "type": "tool",
              "tool": "add_todo", "args": {},
              "triggers": ["пустое дело"], "response": "Записала."})
check("неудачный блок не прикрывается ответом карточки",
      not result.ok and result.message != "Записала.",
      f"| {result.message!r}")

# ---------------------------------------------------------------------------
print()
print("=== старые карточки и узкое горлышко импорта ===")

result = run({"id": "k01_old", "enabled": True, "type": "speak",
              "target": "по-старому", "triggers": ["старое"],
              "response": ""})
check("карточка «Озвучить» работает как прежде",
      result.ok and result.message == "по-старому", f"| {result.message!r}")

narrowed = data_transfer.sanitize_command(
    step("tool", tool="add_todo",
         args={"text": "x" * 5000, "nested": {"a": 1}, "n": 3, "b": True}))
check("импорт оставляет блоку его инструмент",
      narrowed["type"] == "tool" and narrowed["tool"] == "add_todo")
check("и сводит аргументы к тому, что заполняют руками",
      len(narrowed["args"]["text"]) == 1000
      and isinstance(narrowed["args"]["nested"], str)
      and narrowed["args"]["n"] == 3 and narrowed["args"]["b"] is True,
      f"| {narrowed['args'] | {'text': '…'}}")

check("«говорит ли команда» видит вопрос в глубине ветки",
      user_commands.speaks(
          {"type": "sequence", "steps": [
              {"type": "if", "steps": [],
               "otherwise": [step("tool", tool="list_todo")]}]},
          engine._tools.block_effect))
check("а одно действие — не речь",
      not user_commands.speaks(
          {"type": "sequence",
           "steps": [step("tool", tool="add_todo")]},
          engine._tools.block_effect))

print()
print("ИТОГО ошибок:", fails)
sys.exit(1 if fails else 0)
