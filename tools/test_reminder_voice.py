# -*- coding: utf-8 -*-
"""
4.0-E05: a reminder says itself, and warns before the hour.

**The regression this starts from.** 3.1.0 spoke a fired reminder,
showed it and notified: "сказать вслух, показать и уведомить". The port
kept the event and nothing else, and the shell's only use of it was a
tray balloon shown *solely while the window was hidden*. So a reminder
coming due with the window open did nothing observable at all — no
voice, no banner, a row quietly turning grey in a tab nobody was
looking at. On an assistant whose whole point is answering aloud, that
is the one thing an alarm must not be.

It slipped past `4.0-A06` and `R11` because those compared the surface
of the interface, not what happens on an event; and past the recorded
set, which is about parsing a phrase. So the check here is about the
event: something comes due, and Rina is heard.

**Warning before the hour.** Two leads, three hours and one. The
condition that carries the rest is that a lead only counts if the
reminder was **created before that moment** — without it "напомни через
пятнадцать минут" would answer "через час: …" the same second, because
an hour before is already the past.

**And plans in the answer about tasks.** Only when there are any: an
addition that reports an absence turns every answer into two.
"""
import os
import sys
import time

sys.path.insert(0, r"C:\DevStation\PCDev\DesktopApps\RinaAssistant")
sys.path.insert(0, os.path.join(
    r"C:\DevStation\PCDev\DesktopApps\RinaAssistant", "tools"))

from sandbox import neutralise

neutralise(storage=False)

from console import use_utf8
from core.engine import RinaEngine
from core.settings_api import MemorySettings
from voice import reminders as reminders_mod

use_utf8()

fails = 0


def check(label, cond, detail=""):
    global fails
    if not cond:
        fails += 1
    print(("OK   " if cond else "FAIL "), label, detail)


class Session:
    def __init__(self, **extra):
        self.settings = MemorySettings({
            "todo": [], "sessions": [], "custom_commands": [],
            "reminders": [], "history": [], **extra,
        })
        self.engine = RinaEngine(settings=self.settings)
        self.said = []
        self.engine.voice_out = lambda text, **kw: self.said.append(text)

    def say(self, phrase):
        self.said = []
        self.engine.handle_command(phrase, source="typed")
        return " ".join(self.said)

    @property
    def rows(self):
        return self.settings.get("reminders") or []


print("=== сработавшее напоминание слышно ===")
s = Session()
s.say("напомни через 15 минут выключить духовку")
s.said = []
s.engine._fire_reminder(s.rows[0])
heard = " ".join(s.said)
check("сказано вслух", bool(heard), f"| {heard!r}")
check("и сказано, что именно", "духовку" in heard, f"| {heard}")
# A timer announcing itself as «Напоминание» names the wrong
# instrument, and somebody running both cannot tell which went off.
check("вид назван словом", heard.startswith("Напоминание"), f"| {heard}")
check("и помечено сделанным", s.rows[0]["done"] is True)

s = Session()
s.say("засеки 5 минут")
s.said = []
s.engine._fire_reminder([r for r in s.rows if r["kind"] == "timer"][0])
heard = " ".join(s.said)
check("таймер называет себя таймером", heard.startswith("Таймер"),
      f"| {heard}")
check("и говорит, что время вышло", "время вышло" in heard.lower(),
      f"| {heard}")

print()
print("=== предупреждения заранее ===")
s = Session()
s.say("напомни в 23:30 встреча с друзьями")
rows = s.rows
at = rows[0]["fire_at"]
# Created in the morning, so both leads are legitimate. Written rather
# than waited for: a check that slept would measure the machine.
rows[0]["created_at"] = at - 9 * 3600
s.settings.set("reminders", rows)
store = s.engine._reminders


def owed(when):
    s.said = []
    for item, lead in store.ahead_due(now=when):
        s.engine._warn_ahead(item, lead)
    return " ".join(s.said)


check("за четыре часа — молчит", owed(at - 4 * 3600) == "",
      f"| {owed(at - 4 * 3600)}")
three = owed(at - 3 * 3600)
check("за три часа — предупреждает", "3 часа" in three, f"| {three}")
check("и называет время", "23:30" in three, f"| {three}")
check("за два часа — второй раз не повторяет", owed(at - 2 * 3600) == "",
      f"| {owed(at - 2 * 3600)}")
one = owed(at - 3600)
check("за час — предупреждает снова", "час" in one, f"| {one}")
check("за пять минут — молчит", owed(at - 300) == "", f"| {owed(at - 300)}")

# The condition that carries the rest.
s = Session()
s.say("напомни через 15 минут выключить духовку")
short = s.engine._reminders
check("короткое напоминание предупреждений не получает",
      short.ahead_due(now=short.all()[0]["fire_at"] - 60) == [],
      f"| {short.ahead_due(now=short.all()[0]['fire_at'] - 60)}")

# Said leads survive a restart: the field lives on the entry, not in the
# scheduler. Left running overnight, Rina would otherwise say "через три
# часа" again every morning.
s = Session()
s.say("напомни в 23:30 встреча")
rows = s.rows
rows[0]["created_at"] = rows[0]["fire_at"] - 9 * 3600
s.settings.set("reminders", rows)
for item, lead in s.engine._reminders.ahead_due(
        now=rows[0]["fire_at"] - 3 * 3600):
    s.engine._warn_ahead(item, lead)
again = RinaEngine(settings=s.settings)
check("сказанное предупреждение переживает перезапуск",
      again._reminders.ahead_due(now=rows[0]["fire_at"] - 3 * 3600) == [],
      "| после перезапуска сказала бы второй раз")

print()
print("=== что «на сегодня» значит ===")
# Asked of `today()` with a fixed clock rather than of the whole program
# at whatever hour the suite happens to run.
#
# The first edition of this check set a reminder for «23:30» and
# asserted the answer named it. It passed all day and failed at 23:44:
# by then 23:30 is tomorrow, the answer was right to stay quiet, and
# the check was measuring the clock on the wall. The very fault this
# suite spent a day taking out of the shell, written back in by hand.
NOON = time.mktime((2026, 9, 21, 12, 0, 0, 0, 0, -1))
same_day = [{"id": "a", "text": "встреча с друзьями", "on": None,
             "done": False, "fire_at": NOON + 6 * 3600},
            {"id": "b", "text": "вчерашнее", "on": None, "done": False,
             "fire_at": NOON - 3 * 3600},
            {"id": "c", "text": "завтрашнее", "on": None, "done": False,
             "fire_at": NOON + 30 * 3600},
            {"id": "d", "text": "по поводу", "on": {"kind": "app.foreground"},
             "done": False, "fire_at": 0}]
ahead = reminders_mod.today(same_day, now=NOON)
check("сегодняшнее и впереди — попадает",
      [one["text"] for one in ahead] == ["встреча с друзьями"],
      f"| {[one['text'] for one in ahead]}")
said = reminders_mod.say_today(ahead)
check("названо с временем", "встреча с друзьями" in said and "18:00" in said,
      f"| {said}")
check("пусто — молчит", reminders_mod.say_today([]) == "",
      f"| {reminders_mod.say_today([])!r}")

print()
print("=== планы попадают в ответ о делах ===")
s = Session()
answer = s.say("какие задачи на сегодня")
check("без планов про них ни слова",
      "заплан" not in answer.lower(), f"| {answer}")

# The wiring, asked as a rule and not as an outcome: whatever `today()`
# says at this hour, the answer has to agree with it. True at any hour,
# including the twenty minutes before midnight.
s = Session()
s.engine._reminders.add("reminder", time.time() + 20 * 60, "встреча с друзьями")
planned = reminders_mod.today(s.engine._reminders.active())
answer = s.say("какие задачи на сегодня")
check("дел нет — сказано", "дел нет" in answer.lower(), f"| {answer}")
check("ответ согласен с тем, что сегодня есть",
      ("встреча с друзьями" in answer) == bool(planned),
      f"| сегодня {len(planned)}, ответ: {answer}")

s = Session()
s.say("запиши купить хлеб")
s.engine._reminders.add("reminder", time.time() + 20 * 60, "встреча с друзьями")
planned = reminders_mod.today(s.engine._reminders.active())
answer = s.say("какие у нас задачи на сегодня")
check("дело названо", "купить хлеб" in answer, f"| {answer}")
check("и план — если он сегодня",
      ("встреча с друзьями" in answer) == bool(planned),
      f"| сегодня {len(planned)}, ответ: {answer}")

# Tomorrow is not today, at any hour.
s = Session()
s.engine._reminders.add("reminder", time.time() + 30 * 3600, "завтрашнее")
answer = s.say("какие задачи на сегодня")
check("завтрашнее в «сегодня» не попадает",
      "завтрашнее" not in answer, f"| {answer}")

print()
print("ИТОГО ошибок:", fails)
sys.exit(1 if fails else 0)
