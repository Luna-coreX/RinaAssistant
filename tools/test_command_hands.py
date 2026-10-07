# -*- coding: utf-8 -*-
"""
A person's own command launches and opens only through the shell.

Found by the audit of 2026-10-07 (H-2). The voice's "открой …" went to the
shell, which canonicalises the path, refuses Downloads and Temp, asks about
the unsigned and writes the launch journal. A command's steps went past all
of it: `os.startfile`, `webbrowser.open` and `system_control.run` in the
core's own process. A card imported from somebody else's file, once
switched on, could run `Downloads\\setup.exe` without a question.

Checked here, with the shell substituted by a recorder that answers as the
real one does:

- a program, a folder, a Store app, a site and a system action of a command
  all reach the shell, with the kind the shell needs to tell them apart;
- a site is opened as a web address, never as anything else;
- the shell's refusals are said in words, not as "it did not work";
- with no shell nothing is launched at all.

The static half — no `os.startfile` and the like in the module — is in
`tools/test_invariants.py`.

To run:
    python tools/test_command_hands.py
"""
import os
import sys
import tempfile
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

fails = 0


def check(label, cond, detail=""):
    global fails
    if not cond:
        fails += 1
    print(("OK   " if cond else "FAIL "), label, detail)


class Shell:
    """What the core asks of the shell, and the answer to give."""

    def __init__(self, launch=(True, ""), url=(True, "")):
        self.asked = []
        self._launch, self._url = launch, url

    def launch(self, what, kind):
        self.asked.append(("launch", what, kind))
        return self._launch

    def open_url(self, url):
        self.asked.append(("url", url))
        return self._url

    def system(self, action, **extra):
        self.asked.append(("system", action, bool(extra.get("confirmed"))))
        return True, ""


def core_with(shell, commands):
    engine = RinaEngine(settings=MemorySettings({
        "custom_commands": commands, "todo": [], "reminders": [],
        "history": [], "stt_engine": "disabled",
        "web_search_fallback": False}), event_bus=EventBus())
    engine.voice_out = lambda text, **kw: None
    said = []
    engine.bus.on(Events.RESPONSE, lambda data: said.append(data["text"]))
    if shell is not None:
        engine.launch_out = shell.launch
        engine.browser_out = shell.open_url
        engine.system_out = shell.system
    box.paths.clear()
    box.launched.clear()
    box.opened.clear()
    box.actions.clear()
    return engine, said


def card(cid, ctype, target, trigger, **more):
    return dict({"id": cid, "enabled": True, "type": ctype, "target": target,
                 "triggers": [trigger], "match": "exact", "response": "",
                 "steps": []}, **more)


program = sys.executable                       # a file that certainly exists
folder = tempfile.gettempdir()

# ---------------------------------------------------------------------------
print("=== шаги команды доходят до оболочки ===")
shell = Shell()
engine, said = core_with(shell, [
    card("c1", "app", program, "открой питон"),
    card("c2", "folder", folder, "открой папку"),
    card("c3", "app", "Microsoft.WindowsCalculator_8wekyb3d8bbwe!App",
         "открой калькулятор", target_kind="uwp"),
    card("c4", "website", "example.org/путь", "открой сайт"),
    card("c5", "system", "sys_volume_up", "громче, пожалуйста"),
    card("c6", "system", "sys_screenshot", "сними экран"),
])
for phrase in ("открой питон", "открой папку", "открой калькулятор",
               "открой сайт", "громче, пожалуйста", "сними экран"):
    engine.handle_command(phrase, source="typed")
time.sleep(0.2)
check("программа — запуск оболочкой, как файл",
      ("launch", program, "file") in shell.asked, f"| {shell.asked}")
check("папка — оболочкой, и названа папкой",
      ("launch", folder, "folder") in shell.asked)
check("приложение Store — оболочкой, по идентификатору",
      any(a[0] == "launch" and a[2] == "uwp" for a in shell.asked))
check("сайт — оболочкой, как веб-адрес с https",
      ("url", "https://example.org/путь") in shell.asked, f"| {shell.asked}")
check("громкость — оболочкой", ("system", "volume_up", False) in shell.asked)
check("и снимок экрана тоже, а не «успех» без снимка (L-6)",
      ("system", "screenshot", False) in shell.asked)
check("сами ничего не запустили и не открыли",
      not box.paths and not box.launched and not box.opened and not box.actions,
      f"| {box.paths} {box.launched} {box.opened} {box.actions}")

# ---------------------------------------------------------------------------
print()
print("=== отказы оболочки сказаны словами ===")
engine, said = core_with(Shell(launch=(False, "forbidden directory")),
                         [card("c1", "app", program, "открой питон")])
engine.handle_command("открой питон", source="typed")
check("запрещённая папка названа", any("Загрузок" in s for s in said),
      f"| {said}")
engine, said = core_with(Shell(launch=(False, "refused")),
                         [card("c1", "app", program, "открой питон")])
engine.handle_command("открой питон", source="typed")
check("отказ человека — «не стала запускать»",
      any("Не стала запускать" in s for s in said), f"| {said}")

# ---------------------------------------------------------------------------
print()
print("=== без оболочки — ничего ===")
engine, said = core_with(None, [
    card("c1", "app", program, "открой питон"),
    card("c4", "website", "example.org", "открой сайт"),
    card("c5", "system", "sys_volume_up", "громче, пожалуйста")])
for phrase in ("открой питон", "открой сайт", "громче, пожалуйста"):
    engine.handle_command(phrase, source="typed")
time.sleep(0.2)
check("ничего не запущено и не открыто",
      not box.paths and not box.launched and not box.opened and not box.actions,
      f"| {box.paths} {box.launched} {box.opened} {box.actions}")
check("и сказано почему", any("оболочка" in s for s in said), f"| {said}")

print()
print("ИТОГО ошибок:", fails)
sys.exit(1 if fails else 0)
