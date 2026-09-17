# -*- coding: utf-8 -*-
"""
B03: the dialogue's state machine. Checked without the application.

The task's acceptance criterion: the state can be saved and restored.
"""
import json
import os
import sys
import time

sys.path.insert(0, r"C:\DevStation\PCDev\DesktopApps\RinaAssistant")
sys.path.insert(0, os.path.join(
    r"C:\DevStation\PCDev\DesktopApps\RinaAssistant", "tools"))

# The checks do not touch the machine (`4.0-I04`).
#
# Under the interpreter the core actually runs on, `sounddevice` is
# installed — so every answer here played a real cue through the real
# speakers, sixty-nine of them across the suite, and two tests brought
# the process down on the way out. The group "машина" exists precisely
# so that the ordinary run touches nothing; this check belongs to the
# ordinary run.
#
# Storage is left alone: these tests bring their own, and moving it
# would change what they measure rather than what they touch.
from sandbox import neutralise

neutralise(storage=False)

from core.dialog import (CHOOSE_APP, CONFIRM_ACTION, CONFIRM_COMMAND,
                         TTL_SECONDS, Dialog, Question)
from voice.app_index import AppEntry

fails = 0


def check(label, cond, detail=""):
    global fails
    if not cond:
        fails += 1
    print(("OK   " if cond else "FAIL "), label, detail)


print("=== чистота ===")
check("Qt не загружен", "PySide6" not in sys.modules)
check("настройки не загружены", "core.settings_store" not in sys.modules)

print()
print("=== переходы ===")
d = Dialog()
check("сначала пусто", d.current() is None and not d.pending)

d.ask(Question.confirm_action("shutdown"))
check("вопрос задан", d.pending)
check("вид верный", d.current().kind == CONFIRM_ACTION)
check("действие верное", d.current().action == "shutdown")

d.answered()
check("после ответа пусто", d.current() is None)

d.ask(Question.confirm_action("restart"))
d.dropped()
check("после снятия пусто", d.current() is None)

print()
print("=== срок жизни ===")
old = Question(kind=CONFIRM_ACTION, action="shutdown",
               asked_at=time.time() - TTL_SECONDS - 1)
d = Dialog(old)
check("протухший вопрос не действует", d.current() is None)
check("протухший снимается насовсем", d._question is None)

fresh = Question(kind=CONFIRM_ACTION, action="shutdown",
                 asked_at=time.time() - 1)
check("свежий действует", Dialog(fresh).current() is not None)

print()
print("=== сериализация — критерий приёмки ===")
apps = [AppEntry("Visual Studio Code", r"C:\VSCode\Code.exe", "file", "start_menu"),
        AppEntry("Visual Studio 2022", r"C:\VS\devenv.exe", "file", "start_menu")]
d = Dialog()
d.ask(Question.choose_app(apps, query="visual studio"))

raw = json.dumps(d.to_dict(), ensure_ascii=False)
check("состояние пишется в JSON", isinstance(raw, str) and len(raw) > 10)

restored = Dialog.from_dict(json.loads(raw))
q = restored.current()
check("вопрос восстановлен", q is not None and q.kind == CHOOSE_APP)
check("запрос сохранился", q.query == "visual studio")
check("варианты сохранились", len(q.options) == 2)
check("варианты — словари, а не объекты",
      all(isinstance(o, dict) for o in q.options))

entries = q.entries()
check("варианты разворачиваются обратно в объекты",
      [e.name for e in entries] == [a.name for a in apps],
      f"| {[e.name for e in entries]}")
check("путь запуска не потерян", entries[0].launch == apps[0].launch)

for question in (Question.confirm_action("sleep"),
                 Question.confirm_command("cmd-42")):
    again = Question.from_dict(json.loads(json.dumps(question.to_dict())))
    check(f"{question.kind} переживает круг", again == question)

print()
print("=== неизменяемость ===")
q = Question.confirm_action("shutdown")
try:
    q.action = "подмена"
    check("поле защищено", False)
except Exception as e:
    check("поле защищено", True, f"| {type(e).__name__}")

try:
    Question(kind="выдумка")
    check("неизвестный вид отклонён", False)
except ValueError as e:
    check("неизвестный вид отклонён", True, f"| {e}")

print()
print("=== предложенное Риной принимается или отклоняется ===")
# `4.0b-E06`. Rina offers of her own accord — always one setting taking
# one value, and always something the person has just brought about.
# Agreement has to travel the same road as every other "yes": through
# parsing. A second implementation of consent is a second place where
# something can be switched on that nobody asked for.
from core.engine import RinaEngine
from core.settings_api import MemorySettings


def someone(**values):
    store = MemorySettings(dict(
        {"custom_commands": [], "reminders": [], "history": [], "todo": []},
        **values))
    engine = RinaEngine(settings=store)
    spoken = []
    engine.voice_out = lambda text, **rest: spoken.append(text)
    applied = []
    engine.settings_changed = lambda: applied.append(True)
    return engine, store, spoken, applied


engine, store, spoken, applied = someone(tts_engine="silent")
engine.offer("tts_engine", "piper", "Голос Piper",
             "Голос Piper — готово. Включить?")
check("предложение прозвучало", spoken == ["Голос Piper — готово. Включить?"],
      f"| {spoken}")
check("и Рина ждёт ответа", engine._dialog.pending)

engine.handle_command("да", source="voice")
check("согласие включило ровно то, что предлагали",
      store.get("tts_engine") == "piper", f"| {store.get('tts_engine')}")
check("о включении сказано", any("Включила" in line for line in spoken),
      f"| {spoken}")
check("вопрос снят", not engine._dialog.pending)
# A setting written from inside the engine takes a different road from
# `settings.set`, and the voice is rebuilt on that road only: without
# this the person agrees, hears "switched on", and is answered in text
# until the next restart.
check("и тому, кто пересобирает голос, сказано", applied == [True],
      f"| {applied}")

refused, store2, spoken2, _ = someone(tts_engine="silent")
refused.offer("tts_engine", "piper", "Голос Piper", "Включить?")
refused.handle_command("нет", source="voice")
check("отказ ничего не включает",
      store2.get("tts_engine") == "silent", f"| {store2.get('tts_engine')}")
check("и вопрос снят", not refused._dialog.pending)

# The offer goes stale like any other question: agreeing to something
# said a quarter of an hour ago is agreeing to something forgotten.
stale, store3, _, _ = someone(tts_engine="silent")
stale.offer("tts_engine", "piper", "Голос Piper", "Включить?")
stale._dialog._question = stale._dialog._question.__class__(
    **dict(stale._dialog._question.to_dict(), asked_at=time.time() - 3600))
stale.handle_command("да", source="voice")
check("протухшее предложение не срабатывает",
      store3.get("tts_engine") == "silent", f"| {store3.get('tts_engine')}")

print()
print("=== вопрос, который знает, что делать с ответом ===")
# `4.0b-E06`. The kinds before this each knew one action, hard-wired:
# `choose_app` launches, `choose_todo` closes a thing. That stops
# working the moment Rina has to ask something she was not written to
# ask. Now the action travels in the question — an intent's name and
# its arguments — and two ways of reading the answer differ by one
# field.
from core.dialog import ASKED
from core.router import RouterContext, route


def after(question, answer):
    """What one answer to one question turns into."""
    return route(answer, RouterContext(pending=question.to_dict()))


# Without a slot the question is an offer: yes runs the intent as it
# stands, no cancels, anything else withdraws it.
offered = Question.asked("Продолжить работу?", "app.launch",
                         {"app": "Visual Studio Code"})
check("согласие запускает то, что предложили",
      after(offered, "да").name == "app.launch"
      and after(offered, "да").arg("app") == "Visual Studio Code",
      f"| {after(offered, 'да')}")
check("отказ отменяет", after(offered, "нет").name == "cancelled")
check("и «не надо» тоже — это два слова, а не одно",
      after(offered, "не надо").name == "cancelled",
      f"| {after(offered, 'не надо').name}")
check("непонятное ничего не запускает",
      after(offered, "а сколько времени") is None
      or after(offered, "а сколько времени").name != "app.launch")

# With a slot the answer is a value, and the options are suggestions.
asked = Question.asked("Какую музыку?", "music.play", slot="genre",
                       options=("Lo-Fi", "Ambient"))
check("названный вариант понят", after(asked, "Lo-Fi").arg("genre") == "Lo-Fi",
      f"| {after(asked, 'Lo-Fi').arg('genre')!r}")
check("и по месту в списке тоже",
      after(asked, "второе").arg("genre") == "Ambient",
      f"| {after(asked, 'второе').arg('genre')!r}")
# The whole point: a question that only accepts what it named is not a
# question.
check("не названный ответ принят как сказано",
      after(asked, "джаз").arg("genre") == "джаз",
      f"| {after(asked, 'джаз').arg('genre')!r}")
check("и длинный тоже",
      after(asked, "что-нибудь спокойное").arg("genre")
      == "что-нибудь спокойное",
      f"| {after(asked, 'что-нибудь спокойное').arg('genre')!r}")
check("отказ остаётся отказом", after(asked, "не надо").name == "cancelled",
      f"| {after(asked, 'не надо').name}")

# The question is written to a file and sent over the wire like every
# other: the action has to survive that, or it is not a question here.
back = Question.from_dict(asked.to_dict())
check("вопрос с действием переживает запись", back == asked,
      f"| {back.intent}/{back.slot}/{back.options}")

print()
print("ИТОГО ошибок:", fails)
sys.exit(1 if fails else 0)
