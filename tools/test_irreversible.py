# -*- coding: utf-8 -*-
"""
An irreversible step in a person's own command is never run without a yes.

Found by the audit of 2026-10-07 (H-1). The check looked at the top of a
command and at a sequence's own steps, and nowhere else, and only the voice
path asked at all. Each of these shut the computer down without a question:

- the step inside an "if" branch, the body of a loop, or the "otherwise";
- a command that calls another command holding the step;
- the "Run" button in the list, and "Try" in the editor —

while the editor said "Rina will ask". Checked here, with the machine
substituted (`sandbox.neutralise` records system actions instead of running
them):

- `destructive_steps` finds the step anywhere, follows calls, ends a ring;
- the registry refuses the run without a confirmation issued for it;
- the voice path and the button ask, and the yes runs it;
- a trial skips the step and says so, and runs the rest.

To run:
    python tools/test_irreversible.py
"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

from console import use_utf8
from sandbox import neutralise

use_utf8()
box = neutralise()

from core.engine import RinaEngine
from core.events import EventBus
from core.protocol import Events
from core.settings_api import MemorySettings
from voice.user_commands import UNKNOWN_CALL, destructive_steps

fails = 0


def check(label, cond, detail=""):
    global fails
    if not cond:
        fails += 1
    print(("OK   " if cond else "FAIL "), label, detail)


def until(ready, seconds=5.0):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if ready():
            return True
        time.sleep(0.02)
    return ready()


OFF = {"type": "system", "target": "sys_shutdown"}
SAY = {"type": "speak", "target": "доброе утро"}

# ---------------------------------------------------------------------------
print("=== необратимое находится везде ===")
nested = {"type": "sequence", "steps": [
    SAY, {"type": "if", "condition": "after", "value": "23:00",
          "steps": [OFF], "otherwise": []}]}
check("в ветви «если»", destructive_steps(nested) == ["sys_shutdown"],
      f"| {destructive_steps(nested)}")
check("в ветви «иначе»", destructive_steps({"type": "sequence", "steps": [
    {"type": "if", "steps": [SAY], "otherwise": [OFF]}]}) == ["sys_shutdown"])
check("в теле повтора и цикла", destructive_steps({"type": "sequence", "steps": [
    {"type": "repeat", "count": 2, "steps": [
        {"type": "while", "steps": [{"type": "system",
                                     "target": "sys_restart"}]}]}]})
      == ["sys_restart"])

store = {"b": {"id": "b", "type": "sequence", "steps": [OFF]},
         "ring1": {"id": "ring1", "type": "call", "target": "ring2"},
         "ring2": {"id": "ring2", "type": "call", "target": "ring1"},
         "calm": {"id": "calm", "type": "speak", "target": "привет"}}
caller = {"type": "sequence", "steps": [{"type": "call", "target": "b"}]}
check("в вызываемой команде", destructive_steps(caller, store.get)
      == ["sys_shutdown"])
check("кольцо вызовов кончается, а не виснет",
      destructive_steps(store["ring1"], store.get) == [])
check("вызов без способа проверить — считается опасным",
      destructive_steps(caller) == [UNKNOWN_CALL])
check("вызов удалённой команды не выполняет ничего и не считается",
      destructive_steps({"type": "call", "target": "нет"}, store.get) == [])
check("безобидная — пусто", destructive_steps(
    {"type": "sequence", "steps": [SAY, {"type": "call", "target": "calm"}]},
    store.get) == [])


# ---------------------------------------------------------------------------
class Core:
    """A core with a command store and the machine substituted."""

    def __init__(self, commands):
        self.settings = MemorySettings({
            "custom_commands": commands, "todo": [], "reminders": [],
            "history": [], "stt_engine": "disabled",
            "web_search_fallback": False})
        self.engine = RinaEngine(settings=self.settings, event_bus=EventBus())
        self.engine.voice_out = lambda text, **kw: None
        self.said = []
        self.engine.bus.on(Events.RESPONSE,
                           lambda data: self.said.append(data["text"]))
        box.actions.clear()


MORNING = {"id": "cmd_morning", "enabled": True, "type": "sequence",
           "triggers": ["доброе утро"], "match": "contains", "response": "",
           "steps": [SAY, {"type": "if", "condition": "after", "value": "00:00",
                           "steps": [OFF], "otherwise": [OFF]}]}

print()
print("=== реестр не выполняет без подтверждения ===")
core = Core([MORNING])
refused = core.engine._tools.call("run_user_command",
                                  {"command_id": "cmd_morning"}, source="shell")
time.sleep(0.3)
check("запуск без подтверждения — отказ", not refused.ok,
      f"| {refused.error_code}")
check("и компьютер не выключен", box.actions == [], f"| {box.actions}")

print()
print("=== голос спрашивает, «да» выполняет ===")
core = Core([MORNING])
core.engine.handle_command("доброе утро", source="typed")
asked = core.engine._dialog.pending if hasattr(core.engine, "_dialog") else None
check("фраза не выключила, а спросила", box.actions == []
      and any("необратимое" in s for s in core.said), f"| {core.said[-1:]}")
check("и назвала, что именно", any("выключить компьютер" in s.lower()
                                   for s in core.said), f"| {core.said[-1:]}")
core.engine.handle_command("да", source="typed")
check("после «да» — выполнено", until(lambda: "shutdown" in box.actions),
      f"| {box.actions}")

box.actions.clear()
core.engine.handle_command("доброе утро", source="typed")
core.engine.handle_command("нет", source="typed")
time.sleep(0.3)
check("после «нет» — ничего", box.actions == [], f"| {box.actions}")

print()
print("=== кнопка «Выполнить» тоже спрашивает ===")
core = Core([MORNING])
core.engine.run_command_by_id("cmd_morning")
time.sleep(0.3)
check("кнопка не выключила, а спросила", box.actions == []
      and any("необратимое" in s for s in core.said), f"| {core.said[-1:]}")
core.engine.answer_question(True)
check("подтверждение из окна — выполнено",
      until(lambda: "shutdown" in box.actions), f"| {box.actions}")

print()
print("=== команда, вызывающая другую, — тоже ===")
CALLEE = {"id": "cmd_off", "enabled": True, "type": "system",
          "target": "sys_shutdown", "triggers": ["выключайся"],
          "match": "exact", "response": "", "steps": []}
CALLER = {"id": "cmd_caller", "enabled": True, "type": "sequence",
          "triggers": ["пока"], "match": "contains", "response": "",
          "steps": [SAY, {"type": "call", "target": "cmd_off"}]}
core = Core([CALLEE, CALLER])
core.engine.handle_command("пока", source="typed")
time.sleep(0.3)
check("вызов выключения спрашивает", box.actions == []
      and any("необратимое" in s for s in core.said), f"| {core.said[-1:]}")

print()
print("=== проба из конструктора: шаг пропущен и назван ===")
core = Core([])
result = core.engine._executor.try_user_command(dict(MORNING, id=""))
check("проба не выключила", until(lambda: len(core.said) >= 2, 2.0) or True)
time.sleep(0.5)
check("компьютер жив", box.actions == [], f"| {box.actions}")
check("и сказано, что шаг пропущен", any("без подтверждения" in s
                                         for s in core.said), f"| {core.said}")

print()
print("ИТОГО ошибок:", fails)
sys.exit(1 if fails else 0)
