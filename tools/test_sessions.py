# -*- coding: utf-8 -*-
"""
4.0b-A02 and 4.0b-A05: working sessions, and focus inside one.

The check goes through `RinaEngine`, because a session has the same
joints as a thing to do and each of them can part company quietly.
Parsing has to take a session's words without taking anybody else's;
the store has to hold at most one open session; and the answers have to
be right about a stretch of time that has not ended yet.

**Three assertions carry the rest.**

*Opening one while another is open is refused.* Quietly closing the
previous one would end a stretch of work at a moment nobody chose, and
the record would say it ended when the next one began — a wrong number
in a page whose whole point is to be believed.

*A session steals nothing.* The stage sits third in the chain, ahead of
the list, the reminders and the system actions, and an early stage is
the ordinary way a phrase stops meaning what it meant. The recorded set
(`docs/golden/utterances.json`) holds that for the 134 phrases it knows;
here the neighbours most at risk are asked one by one, because "запиши"
and "включи" are the two words a session comes closest to.

*Focus is a property of a session, not a mode of the program.* Asked for
without one, it does not invent a session to hold it.
"""
import os
import sys

sys.path.insert(0, r"C:\DevStation\PCDev\DesktopApps\RinaAssistant")
sys.path.insert(0, os.path.join(
    r"C:\DevStation\PCDev\DesktopApps\RinaAssistant", "tools"))

# The checks do not touch the machine (`4.0-I04`); storage is left alone
# because this one brings its own.
from sandbox import neutralise

neutralise(storage=False)

from console import use_utf8
from core.engine import RinaEngine
from core.settings_api import MemorySettings
from voice import sessions as sessions_mod

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
            "todo": [], "sessions": [], "custom_commands": [],
            "reminders": [], "history": [],
        })
        self.engine = RinaEngine(settings=self.settings)
        self.said = []
        self.engine.voice_out = lambda text, **kw: self.said.append(text)
        self.opened = []
        self.engine.browser_out = lambda url: (self.opened.append(url),
                                               (True, ""))[1]

    def say(self, phrase):
        self.said = []
        self.engine.handle_command(phrase, source="typed")
        return " ".join(self.said)

    @property
    def rows(self):
        return self.settings.get("sessions") or []


print("=== сессия открывается, живёт и закрывается ===")
s = Session()
answer = s.say("начни сессию над протоколом")
check("сессия открылась", len(s.rows) == 1, f"| {len(s.rows)}")
check("и названа так, как сказано",
      s.rows and s.rows[0]["goal"] == "над протоколом",
      f"| {s.rows[0]['goal'] if s.rows else ''}")
# Russian declines and Rina does not. The tail is kept whole, preposition
# and all, so that the answer fits the frame the person used: strip "над"
# and every sentence comes back as «Начала сессию «протоколом»».
check("и ответ по-русски звучит", "над протоколом" in answer, f"| {answer}")

answer = s.say("запиши в сессию конверт готов")
check("заметка легла в сессию",
      s.rows[0]["notes"] == ["конверт готов"], f"| {s.rows[0]['notes']}")
check("и это не стало делом", not (s.settings.get("todo") or []),
      f"| {s.settings.get('todo')}")

answer = s.say("какая сессия")
check("открытая сессия называется", "над протоколом" in answer, f"| {answer}")
check("и говорит, сколько идёт",
      "минут" in answer or "мин" in answer, f"| {answer}")

answer = s.say("заверши сессию и запиши апи готово")
check("сессия закрылась", s.rows[0]["finished"] > 0, f"| {s.rows[0]}")
check("и закрывающая заметка записана",
      s.rows[0]["notes"] == ["конверт готов", "апи готово"],
      f"| {s.rows[0]['notes']}")
check("а в ответе сказано, что было", "конверт готов" in answer, f"| {answer}")

print()
print("=== вторая сессия поверх открытой не заводится ===")
s = Session()
s.say("начни сессию над протоколом")
answer = s.say("начни сессию над макетом")
check("вторая не завелась", len(s.rows) == 1, f"| {len(s.rows)}")
# Quietly closing the first one is the failure this guards. It would end
# a stretch of work at a moment nobody chose, and nothing would say so.
check("первая не закрылась исподтишка", s.rows[0]["finished"] == 0,
      f"| {s.rows[0]['finished']}")
check("и сказано, какая идёт", "над протоколом" in answer, f"| {answer}")

print()
print("=== закрывать нечего — так и сказано ===")
s = Session()
answer = s.say("заверши сессию")
check("пустое закрытие не ломается", not s.rows, f"| {s.rows}")
check("и объясняет себя", "нет открытой" in answer.lower(), f"| {answer}")
answer = s.say("что я делал в прошлой сессии")
check("прошлого тоже нет, и это сказано",
      "нет" in answer.lower(), f"| {answer}")

print()
print("=== сколько ушло ===")
s = Session()
s.say("начни сессию над протоколом")
# The clock is not waited on: the store is told when the session ended.
# A check that slept would measure the machine rather than the counting,
# and would flake on a busy one.
store = s.engine.sessions
open_one = store.current()
store.finish(now=open_one["started"] + 2 * 3600 + 15 * 60)
answer = s.say("сколько я работал над протоколом")
check("время сосчитано", "2 ч 15 мин" in answer, f"| {answer}")
check("и сессия одна", "1" in answer, f"| {answer}")

answer = s.say("сколько я работал над чем-то другим")
check("про незнакомое — ничего не записано",
      "ничего не записано" in answer.lower(), f"| {answer}")

print()
print("=== фокус живёт внутри сессии (4.0b-A05) ===")
s = Session()
answer = s.say("включи режим фокуса")
check("без сессии фокус не включается", not s.rows, f"| {s.rows}")
check("и сказано, чего не хватает", "сесси" in answer.lower(), f"| {answer}")

s.say("начни сессию над протоколом")
s.say("включи режим фокуса")
check("в сессии фокус включается", s.rows[0]["focus"] is True,
      f"| {s.rows[0]['focus']}")
check("и движок про это знает", s.engine.sessions.focused())

s.say("выключи режим фокуса")
check("и выключается", s.rows[0]["focus"] is False, f"| {s.rows[0]['focus']}")
# "выключи режим фокуса" contains "режим фокуса". Taken in the other
# order, every request to stop would start it.
check("«выключи» не включает обратно", not s.engine.sessions.focused())

s.say("включи режим фокуса")
s.say("заверши сессию")
check("закрытая сессия не остаётся в фокусе",
      s.rows[0]["focus"] is False, f"| {s.rows[0]['focus']}")

print()
print("=== соседи по цепочке не задеты ===")
s = Session()
s.say("запиши купить хлеб")
check("«запиши» по-прежнему дело",
      len(s.settings.get("todo") or []) == 1,
      f"| {s.settings.get('todo')}")
check("и не сессия", not s.rows, f"| {s.rows}")

s = Session()
answer = s.say("начни сессию")
check("«начни сессию» без цели не заводит сессию", not s.rows, f"| {s.rows}")
# A phrase this stage refuses goes on down the chain and ends in a web
# search. Proved by breaking it: that is what "запиши" did until the
# list's own check asked about the browser.
check("и не уходит в браузер", not s.opened, f"| {s.opened}")
check("а говорит, чего не хватило", "начать" in answer.lower(), f"| {answer}")

print()
print("=== хроника приложений (T-22) ===")
# Three conditions, and the check asks about each on its own. Two of
# them are switches a person sets, and a switch that does not actually
# switch anything off is the worst kind: it reads as consent given.
def chronicle(watch, record, session=True):
    st = MemorySettings({"todo": [], "sessions": [], "custom_commands": [],
                         "reminders": [], "history": [],
                         "watch_apps": watch, "session_apps": record})
    eng = RinaEngine(settings=st)
    eng.voice_out = lambda text, **kw: None
    if session:
        eng.handle_command("начни сессию над протоколом", source="typed")
    eng._credit_foreground(r"C:\Program Files\Code.exe", now=1000.0)
    eng._credit_foreground(r"C:\Windows\explorer.exe", now=1000.0 + 25 * 60)
    eng._credit_foreground(r"C:\Program Files\Code.exe", now=1000.0 + 30 * 60)
    rows = st.get("sessions") or []
    return rows[0]["apps"] if rows else {}


apps = chronicle(watch=True, record=True)
check("время начисляется уходящей программе",
      apps == {"Code": 1500.0, "explorer": 300.0}, f"| {apps}")
# A path names a place on somebody's disk, and a session is read back
# to them out loud.
check("и программа названа именем, а не путём",
      all("\\" not in name and ".exe" not in name for name in apps),
      f"| {list(apps)}")

check("без session_apps не пишется ничего",
      chronicle(watch=True, record=False) == {},
      f"| {chronicle(watch=True, record=False)}")
check("и без открытой сессии тоже",
      chronicle(watch=True, record=True, session=False) == {},
      f"| {chronicle(watch=True, record=True, session=False)}")

# T-22 says the chronicle is not in the diagnostic package, and the
# package is built by walking `settings.describe()`. So the claim comes
# to this: sessions are not a setting.
from core import settings_schema
check("сессии не настройка — значит не в диагностическом пакете",
      "sessions" not in settings_schema.SETTABLE
      and "sessions" not in (settings_schema.describe() or {}),
      "| sessions попала в describe()")
check("а выключатели — настройка, и это верно",
      "session_apps" in settings_schema.SETTABLE
      and "session_folders" in settings_schema.SETTABLE)

print()
print("=== отданные команды попадают в сессию ===")
s = Session()
s.say("начни сессию над протоколом")
s.say("который час")
check("команда записана",
      s.rows[0]["commands"] == ["который час"], f"| {s.rows[0]['commands']}")
# A phrase that turned out not to be addressed to her is not a command
# that was given.
s.engine.handle_command("выключи компьютер", require_wake=True, source="voice")
check("нерасслышанное командой не считается",
      s.rows[0]["commands"] == ["который час"], f"| {s.rows[0]['commands']}")

print()
print("=== фокус придерживает, а не теряет (4.0b-A05) ===")
s = Session()
s.say("начни сессию над протоколом")
s.say("включи режим фокуса")
s.said = []
s.engine.offer("tts_engine", "piper", "Голос Piper",
               "Голос Piper — готово. Включить?")
check("в фокусе предложение молчит", not s.said, f"| {s.said}")
answer = s.say("заверши сессию")
check("и звучит при закрытии", "Голос Piper" in answer, f"| {answer}")
# Before it, and the offer would come out ahead of the closing — the
# wrong order for something that has waited an hour.
check("после закрытия, а не перед ним",
      answer.index("Сессия закрыта") < answer.index("Голос Piper"),
      f"| {answer}")
check("и вопрос остался стоять", "Включила" in s.say("да"), f"| {s.said}")

print()
print("=== разбор фраз сам по себе ===")
for phrase, expect in (
        ("начни сессию над протоколом", "start"),
        ("начинаю работать над макетом", "start"),
        ("заверши сессию", "finish"),
        ("конец сессии", "finish"),
        ("что я делал в прошлой сессии", "last"),
        ("какая сессия", "current"),
        ("пометь в сессии конверт готов", "note"),
        ("сколько времени ушло на макет", "worked"),
        ("не отвлекай", "focus_on"),
        ("выключи режим фокуса", "focus_off"),
        ("который час", None),
        ("запусти телеграм", None),
        ("запиши купить хлеб", None),
        ("напомни через 15 минут", None),
):
    got = sessions_mod.parse(phrase)
    name = got[0] if got else None
    check(f"«{phrase}» -> {expect}", name == expect, f"| {name}")

print()
print("ИТОГО ошибок:", fails)
sys.exit(1 if fails else 0)
