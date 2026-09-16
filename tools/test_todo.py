# -*- coding: utf-8 -*-
"""
4.0b-A13: things to do — what waits, rather than what fires.

The check goes through `RinaEngine`: the task has the same three joints as
the reminders, and each of them can part company silently. Parsing separates
a thing to do from a reminder; the store has to survive an entry with no
clock; closing has to find what was named and **not** find somebody else's.

**The main assertion is about the boundary with reminders.** Merging them
would mean either making a thing to do pretend to be a reminder for a while,
or creating a reminder that will never fire. `4.0b-A03` avoids the second
deliberately, and here it is checked that a phrase with a deadline still
goes to the reminders while one without goes to the list.
"""
import os
import sys

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

from console import use_utf8
from core.engine import RinaEngine
from core.settings_api import MemorySettings

use_utf8()

fails = 0


def check(label, cond, detail=""):
    global fails
    if not cond:
        fails += 1
    print(("OK   " if cond else "FAIL "), label, detail)


class Session:
    """A core with a stand-in store and no way out to the machine."""

    def __init__(self):
        self.settings = MemorySettings({
            "todo": [], "custom_commands": [], "reminders": [], "history": [],
        })
        self.engine = RinaEngine(settings=self.settings)
        self.said = []
        self.engine.voice_out = lambda text, **kw: self.said.append(text)
        # Nothing is opened on the machine this is run on.
        self.opened = []
        self.engine.browser_out = lambda url: (self.opened.append(url),
                                               (True, ""))[1]

    def say(self, phrase):
        self.said = []
        self.engine.handle_command(phrase, source="typed")
        return " ".join(self.said)

    @property
    def todo(self):
        return self.settings.get("todo") or []


print("=== дело заводится и живёт ===")
s = Session()
answer = s.say("запиши купить хлеб")
check("дело записано", "купить хлеб" in answer, f"| {answer}")
check("и лежит в хранилище",
      [i["text"] for i in s.todo] == ["купить хлеб"], f"| {s.todo}")
check("и оно открыто", s.todo[0]["done"] is False)
# A thing to do has no clock at all, rather than a zero: zero is the year
# 1970, and anybody comparing it with the time would find it half a century
# overdue.
check("часов у дела нет", "fire_at" not in s.todo[0], f"| {sorted(s.todo[0])}")

print()
print("=== список отвечает по-разному на пусто и не пусто ===")
empty = Session()
check("без дел так и сказано", "нет" in empty.say("какие дела").lower(),
      f"| {empty.say('какие дела')}")
s.say("запиши позвонить маме")
listed = s.say("какие дела")
check("оба дела названы",
      "хлеб" in listed and "маме" in listed, f"| {listed}")

print()
print("=== закрытие ===")
answer = s.say("сделал хлеб")
check("закрытое названо по имени", "хлеб" in answer, f"| {answer}")
check("и помечено сделанным",
      [i["done"] for i in s.todo if "хлеб" in i["text"]] == [True],
      f"| {s.todo}")
check("в списке его больше нет", "хлеб" not in s.say("какие дела"))
# Closing does not delete: a person changes their mind, and something that
# vanished can neither be brought back nor remembered.
check("но из хранилища не пропало", len(s.todo) == 2, f"| {len(s.todo)}")

answer = s.say("сделал молоко")
check("ненайденное дело названо своим ответом",
      "молоко" in answer and "не нашла" in answer.lower(), f"| {answer}")
# Otherwise a person who hears "nothing on the list" will decide the whole
# list has gone.
check("а не сообщением о пустом списке", "дел нет" not in answer.lower(),
      f"| {answer}")

print()
print("=== когда подходит несколько — спрашивает, а не выбирает ===")
# `4.0b-E06`. Closing the wrong thing is the mistake a person does not
# catch: a closed thing simply leaves the list, and nothing says which one
# went. So when the words fit more than one, the choice goes back to
# whoever owns it.
many = Session()
many.say("запиши купить молоко и хлеб")
many.say("запиши вернуть молоко соседу")
answer = many.say("сделал молоко")
check("не закрыла ничего сама",
      [i["done"] for i in many.todo] == [False, False], f"| {many.todo}")
check("а перечислила и спросила",
      "молоко и хлеб" in answer and "вернуть молоко" in answer
      and "?" in answer, f"| {answer}")
check("и ждёт ответа", many.engine._dialog.pending)

answer = many.say("второе")
check("ответ по месту в списке закрыл нужное",
      [i["done"] for i in many.todo] == [False, True], f"| {many.todo}")
check("и сказано, какое именно", "соседу" in answer, f"| {answer}")
check("вопрос снят", not many.engine._dialog.pending)

# By words as well as by place: a person answers with the part that tells
# the two apart, not with the whole line they never said in the first place.
words = Session()
words.say("запиши купить молоко и хлеб")
words.say("запиши вернуть молоко соседу")
words.say("сделал молоко")
words.say("купить")
check("ответ словами тоже понят",
      [i["done"] for i in words.todo] == [True, False], f"| {words.todo}")

# And a refusal closes nothing at all.
nope = Session()
nope.say("запиши купить молоко и хлеб")
nope.say("запиши вернуть молоко соседу")
nope.say("сделал молоко")
nope.say("неважно")
check("отказ не закрывает ничего",
      [i["done"] for i in nope.todo] == [False, False], f"| {nope.todo}")
check("и вопрос снят", not nope.engine._dialog.pending)

# The exact word still wins outright: "молоко" must close the thing called
# exactly that, not ask about the longer line standing beside it.
exact = Session()
exact.say("запиши молоко")
exact.say("запиши купить молоко и хлеб")
answer = exact.say("сделал молоко")
check("точное совпадение закрывается без вопросов",
      [i["done"] for i in exact.todo] == [True, False], f"| {exact.todo}")

print()
print("=== граница с напоминаниями держится ===")
s2 = Session()
s2.say("напомни через 5 минут позвонить маме")
check("фраза со сроком ушла к напоминаниям",
      len(s2.settings.get("reminders") or []) == 1
      and not s2.todo,
      f"| дел {len(s2.todo)}, напоминаний "
      f"{len(s2.settings.get('reminders') or [])}")

s2.say("запиши позвонить маме")
check("а без срока — к делам",
      len(s2.todo) == 1
      and len(s2.settings.get("reminders") or []) == 1,
      f"| дел {len(s2.todo)}, напоминаний "
      f"{len(s2.settings.get('reminders') or [])}")

# The order of the stages holds nothing — proved by breaking it: swap them
# and everything stays green. What holds is the vocabulary, and here it is.
from core.router import _reminder, _todo, RouterContext            # noqa: E402

probe = RouterContext(todo_find=lambda said: None)
overlap = [phrase for phrase in
           ("запиши купить хлеб", "надо купить хлеб", "не забыть купить хлеб",
            "какие дела", "нужно сделать отчёт")
           if _reminder(phrase, probe) is not None]
check("словари не пересекаются", not overlap, f"| обе берут: {overlap}")
check("«напомни» осталось за напоминаниями",
      _todo("напомни купить хлеб", probe) is None,
      "| дела забрали слово напоминаний")

print()
print("=== два ядра не делят дела ===")
a, b = Session(), Session()
a.say("запиши только моё")
check("соседнее ядро ничего не увидело", not b.todo, f"| {b.todo}")

print()
print("=== недоговорённое не записывается и не ищется ===")
c = Session()
answer = c.say("запиши")
check("«запиши» без продолжения — не дело", not c.todo, f"| {c.todo}")
# A person started to speak and thought better of it. Refusing the phrase
# in the parsing was tempting and made things worse: what is not parsed goes
# on down the stages and ends in a web search for "запиши". Proved by
# breaking it — that is exactly what happened until this check asked about
# the browser.
check("и не открывает браузер", not c.opened, f"| {c.opened}")
check("а говорит, чего не хватило",
      "записать" in answer.lower(), f"| {answer}")

print()
print("ИТОГО ошибок:", fails)
sys.exit(1 if fails else 0)
