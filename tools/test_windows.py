# -*- coding: utf-8 -*-
"""
4.0b-K08: other programs' windows — close, minimise, expand.

The shell is substituted: what it is asked is recorded and its answer is
written here. Checked:

- which phrases are about windows, and which are left to the stages that
  own them («закрой сессию», «закрой дело», reminders) or are not commands
  at all («я не могу закрыть окно»);
- what goes to the shell: the window in front, every window, or a program
  named — with the index's candidates, a word taught for «открой», and the
  name without its case ending («окно хрома»);
- what Rina says for each of the shell's answers, including a program
  that went to the tray and one that is asking about unsaved work;
- «закрой все окна» is confirmed, and Rina herself and a browser's tab are
  not windows to close.

To run:
    python tools/test_windows.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

from console import use_utf8
from sandbox import neutralise

use_utf8()
neutralise()

from core.protocol import Events
from core.router import RouterContext, route
from core.toolrunner import ToolContext, ToolRunner
from golden_runner import FAKE_APPS
from voice import app_index, windows

fails = 0


def check(label, cond, detail=""):
    global fails
    if not cond:
        fails += 1
    print(("OK   " if cond else "FAIL "), label, detail)


# ---------------------------------------------------------------------------
print("=== какие фразы — про окна ===")
for phrase, expected in (
        ("закрой дискорд", ("close", "дискорд")),
        ("Закрой Discord.", ("close", "discord")),
        ("закрой", ("close", "active")),
        ("закрой окно", ("close", "active")),
        ("закрой это окно", ("close", "active")),
        ("сверни", ("minimize", "active")),
        ("сверни телеграм", ("minimize", "телеграм")),
        ("разверни хром", ("expand", "хром")),
        ("разверни хром на весь экран", ("maximize", "хром")),
        ("разверни на весь экран", ("maximize", "active")),
        ("закрой окно хрома", ("close", "хрома")),
        ("сверни все окна", ("minimize", "all")),
        ("сверни всё", ("minimize", "all")),
        ("сверни окна", ("minimize", "all")),
        ("верни окна", ("restore", "all")),
        ("разверни все окна", ("restore", "all")),
        ("закрой все окна", ("close", "all")),
        ("пожалуйста закрой дискорд", ("close", "дискорд")),
        ("close discord", ("close", "discord")),
        ("minimize all windows", ("minimize", "all")),
        ("restore discord", ("expand", "discord"))):
    got = windows.classify(phrase)
    check(f"«{phrase}» → {expected}", got == expected, f"| {got}")

for phrase in ("я не могу закрыть окно", "верни дискорд", "открой дискорд",
               "сверни на весь экран", "погода"):
    check(f"«{phrase}» — не про окна", windows.classify(phrase) is None,
          f"| {windows.classify(phrase)}")

print()
print("=== фразы, у которых есть свой хозяин ===")
for phrase, owner in (("закрой сессию", "session.finish"),
                      ("напомни закрыть дискорд через 5 минут",
                       "reminder.create"),
                      ("закрой все окна", "system.confirm"),
                      ("сверни все окна", "windows.all"),
                      ("закрой дискорд", "windows.control")):
    name = route(phrase, RouterContext()).name
    check(f"«{phrase}» → {owner}", name == owner, f"| {name}")
check("«закрой дело …» — делам, не окнам",
      route("закрой дело купить хлеб", RouterContext()).name.startswith("todo."))
check("подтверждение — именно закрытия всех окон",
      route("закрой всё", RouterContext()).args
      == {"action": "windows_close_all"})

# ---------------------------------------------------------------------------
print()
print("=== что уходит оболочке ===")


class Settings(dict):
    def get(self, key, default=None):
        return super().get(key, default)


asked, emitted = [], []
answer = {}
apps = [app_index.AppEntry(*a) for a in FAKE_APPS]
settings = Settings(app_aliases={
    "код": {"path": __file__, "kind": "file", "name": "Visual Studio Code"}})


def shell(action, target):
    asked.append((action, dict(target)))
    return dict(answer)


runner = ToolRunner(ToolContext(
    settings=settings, apps=lambda: apps, windows_out=shell,
    emit=lambda name, **data: emitted.append((name, data))))


def call(name, **args):
    return runner.call(name, args, source="typed")


answer = {"ok": True, "program": "Discord", "done": 1}
call("window_control", action="close", app="дискорд")
action, target = asked[-1]
check("названная программа уходит кандидатами из индекса",
      [a["name"] for a in target["apps"]] == ["Discord"]
      and target["which"] == "app", f"| {target}")
check("и именем в написаниях индекса — для того, чего в индексе нет",
      "diskord" in target["names"], f"| {target['names']}")

call("window_control", action="minimize", app="хрома")
check("«окно хрома» — Chrome: окончание отброшено",
      [a["name"] for a in asked[-1][1]["apps"]] == ["Google Chrome"],
      f"| {asked[-1][1]}")

call("window_control", action="close", app="код")
check("выученное для «открой» слово работает и для «закрой»",
      asked[-1][1]["apps"][:1] == [{"name": "Visual Studio Code",
                                    "launch": __file__, "kind": "file"}],
      f"| {asked[-1][1]['apps'][:1]}")

call("window_control", action="close", app="visual studio")
check("неоднозначное в индексе уходит всеми кандидатами — какая из них "
      "открыта, знает оболочка",
      {"Visual Studio Code", "Visual Studio 2022"}
      <= {a["name"] for a in asked[-1][1]["apps"]}, f"| {asked[-1][1]['apps']}")

call("window_control", action="close")
check("без программы — окно впереди", asked[-1] == ("close", {"which": "active"}))

# ---------------------------------------------------------------------------
print()
print("=== что Рина говорит ===")


def says(shell_answer, name="window_control", **args):
    global answer
    answer = shell_answer
    return call(name, **args)


for label, shell_answer, args, expected, ok in (
        ("закрыла", {"ok": True, "program": "Discord", "done": 1},
         {"action": "close", "app": "дискорд"}, "Закрыла Discord.", True),
        ("в трее — так и сказано",
         {"ok": True, "program": "Discord", "done": 1, "still_running": True},
         {"action": "close", "app": "дискорд"},
         "Закрыла окно Discord, а сама программа осталась работать в трее — "
         "так она устроена.", True),
        ("спрашивает о несохранённом — так и сказано",
         {"ok": True, "program": "Блокнот", "done": 0, "left": 1},
         {"action": "close", "app": "блокнот"},
         "Блокнот что-то спрашивает перед закрытием — посмотри на экран.", True),
        ("свернула окно впереди — по имени программы",
         {"ok": True, "program": "Telegram", "done": 1},
         {"action": "minimize"}, "Свернула Telegram.", True),
        ("на весь экран", {"ok": True, "program": "Google Chrome", "done": 1},
         {"action": "maximize", "app": "хром"},
         "Развернула Google Chrome на весь экран.", True),
        ("не открыта", {"ok": False, "reason": "not_running"},
         {"action": "close", "app": "дискорд"},
         "Не нашла открытых окон «дискорд».", False),
        ("впереди ничего", {"ok": False, "reason": "no_window"},
         {"action": "close"}, "Сейчас впереди нет окна.", False),
        ("несколько подходящих",
         {"ok": False, "reason": "ambiguous",
          "programs": ["Visual Studio Code", "Visual Studio 2022"]},
         {"action": "close", "app": "студию"},
         "Открыто несколько подходящих: Visual Studio Code, Visual Studio 2022. "
         "Назови точнее.", False),
        ("от администратора",
         {"ok": False, "reason": "refused", "program": "Steam"},
         {"action": "close", "app": "стим"},
         "Окно Steam работает с правами администратора, и мне оно не "
         "подчиняется.", False)):
    result = says(shell_answer, **args)
    check(label, result.ok == ok and result.message == expected,
          f"| {result.ok} {result.message!r}")

result = says({"ok": True, "done": 5}, "all_windows", action="minimize")
check("свернуть все", result.ok and result.message == "Свернула все окна.",
      f"| {result.message}")
check("и ушло оболочке как «все»", asked[-1] == ("minimize", {"which": "all"}))
result = says({"ok": True, "done": 0}, "all_windows", action="restore")
check("вернуть, когда свёрнутых нет", result.message == "Свёрнутых окон нет.",
      f"| {result.message}")

# ---------------------------------------------------------------------------
print()
print("=== закрыть все — только с подтверждением ===")
asked.clear()
answer = {"ok": True, "done": 6, "left": 2}
unconfirmed = call("close_all_windows")
check("без подтверждения не выполняется, оболочку не спрашивают",
      not unconfirmed.ok and unconfirmed.error_code == "confirmation.required"
      and not asked, f"| {unconfirmed.error_code} {asked}")
issued = runner.request_confirmation("close_all_windows", {})
done = runner.call("close_all_windows", {}, confirmation_id=issued.id,
                   source="typed")
check("с подтверждением — закрыто, и названо, сколько ещё спрашивают",
      done.ok and done.message == "Закрыла окна: 6. Ещё спрашивают перед "
      "закрытием: 2 — посмотри на экран.", f"| {done.message!r}")
answer = {"ok": True, "done": 3, "refused": 1}
issued = runner.request_confirmation("close_all_windows", {})
done = runner.call("close_all_windows", {}, confirmation_id=issued.id,
                   source="typed")
check("окна «от администратора» — отказали, а не «спрашивают»",
      done.ok and "администратора" in done.message
      and "спрашивают" not in done.message, f"| {done.message!r}")

# ---------------------------------------------------------------------------
print()
print("=== не окна ===")
asked.clear()
result = says({"ok": True}, action="close", app="вкладку")
check("вкладка — не окно, и оболочку не спрашивают",
      not result.ok and "Вкладками" in result.message and not asked,
      f"| {result.message}")
result = says({"ok": True}, action="close", app="рину")
check("себя Рина так не закрывает — и говорит, как",
      not result.ok and "«Выйти»" in result.message and not asked,
      f"| {result.message}")
emitted.clear()
result = says({"ok": True}, action="minimize", app="рину")
check("а свернуть себя — может, своим окном",
      result.ok and emitted == [(Events.WINDOW_ACTION, {"action": "minimize"})]
      and not asked, f"| {emitted}")

runner_alone = ToolRunner(ToolContext(settings=settings, apps=lambda: apps))
alone = runner_alone.call("window_control", {"action": "close"}, source="typed")
check("без оболочки — так и сказано", not alone.ok and "оболочка" in alone.message,
      f"| {alone.message}")

print()
print("ИТОГО ошибок:", fails)
sys.exit(1 if fails else 0)
