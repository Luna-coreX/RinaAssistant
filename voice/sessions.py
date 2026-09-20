# -*- coding: utf-8 -*-
"""
Working sessions: what a person is at, and for how long.

Plan items `4.0b-A02` and `4.0b-A05`.

**What a session is, and what it is not.** A session is a stretch of work
with a name: a person says what they are starting on, Rina keeps the
context beside it, and at the end there is a record of what happened. It
is not a timer and not a task: a timer fires, a task waits, and a session
merely **is open** until somebody closes it. The three are deliberately
three stores — merging them would mean giving every session a deadline it
has not got, the same reason `4.0b-A13` keeps things to do apart from
reminders.

**The dependency was ambiguous in the plan, and the plan said how to read
it.** `4.0b-A02` was written as depending on `B08` with no prefix, and
there are two: `4.0-B08` (FeatureProvider, closed) and `5.0-B08` (the
context assembler, not begun). The plan settled it in advance — for a
prefix-less entry inside the beta, the beta's own milestone is meant — so
nothing here waits on 5.0. The store is the settings store, as with
things to do; there is no database, and the context is assembled by this
module out of what it was told.

**Watching costs, and the cost is the reason it is a setting.** Time per
application comes from the foreground watcher that `4.0b-A03` already
built and `T-19` already describes. A session goes further than A03 did:
A03 reacted to a change and forgot it, a session **writes it down**. That
is a wider record about a person than anything else Rina keeps, so it is
off until switched on, visible while it runs, listed in "what Rina knows
about me", and forgettable one session at a time.

**Focus mode (`4.0b-A05`) is a session with the sound turned down.** Not
a second mechanism: the same open session, with a flag that suppresses
what Rina says of her own accord. Offers, finished-job reports and
anything else she raises herself wait until the session closes, and then
she reports once. What a person asks for is answered as always —
silencing the answers would make the mode a way to break her.

There is no Qt here: the module lies in the core.
"""

import time
import uuid

from core.i18n import t as tr
from voice.textmatch import normalize


#: Opening a session.
#:
#: "начни" rather than "запусти": the launching stage owns "запусти", and
#: one word given to two things makes a person guess which they will get.
START_WORDS = ("начни сессию", "начинаю сессию", "начни работу над",
               "начинаю работать над", "открой сессию", "сажусь за")

#: Closing it.
FINISH_WORDS = ("заверши сессию", "закончи сессию", "конец сессии",
                "закрой сессию", "сессия окончена")

#: Asking about the one before.
LAST_WORDS = ("что я делал в прошлой сессии", "что было в прошлой сессии",
              "чем я занимался в прошлой сессии", "прошлая сессия",
              "что я делал в прошлый раз")

#: Asking what is open now.
CURRENT_WORDS = ("какая сессия", "текущая сессия", "что у меня открыто",
                 "чем я занят сейчас")

#: Adding a note to the open one.
#:
#: "запиши" is absent on purpose — it belongs to things to do. A note to
#: a session has to say so.
NOTE_WORDS = ("заметка к сессии", "пометь в сессии", "запиши в сессию",
              "добавь к сессии")

#: Naming the folder the work is happening in.
#:
#: Named rather than observed. A window change carries the path of the
#: **program**, which is where it was installed and not where anybody is
#: working; guessing a working folder from it would put `Program Files`
#: into the record and call it a project. So the person says it, and the
#: setting decides whether it is kept at all — saying it once is not the
#: same as agreeing that paths live in the record.
FOLDER_WORDS = ("рабочий каталог", "работаю в каталоге", "работаю в папке",
                "рабочая папка")

#: How long something took.
WORKED_WORDS = ("сколько я работал над", "сколько времени ушло на",
                "сколько я потратил на", "сколько работал над")

#: Focus mode on and off (`4.0b-A05`).
FOCUS_ON_WORDS = ("режим фокуса", "включи фокус", "не отвлекай",
                  "включи режим фокуса")
FOCUS_OFF_WORDS = ("выключи фокус", "выключи режим фокуса",
                   "хватит фокуса", "можешь отвлекать")

#: A week, for "how much this week".
WEEK = 7 * 24 * 60 * 60


def parse(text):
    """
    A phrase -> what to do about sessions, or None.

    Returns `(what, rest)`. The parsing is pure: it knows nothing about
    which sessions exist. Whether one is open is the store's business,
    and the answer to "finish it" when none is open belongs to whoever
    holds the store — the same division as things to do.
    """
    if not text:
        return None
    low = normalize(text)
    if not low:
        return None

    # Off before on: "выключи режим фокуса" contains "режим фокуса", and
    # taken in the other order every request to stop would start it.
    for word in FOCUS_OFF_WORDS:
        if word in low:
            return "focus_off", ""
    for word in FOCUS_ON_WORDS:
        if word in low:
            return "focus_on", ""

    for word in FINISH_WORDS:
        if word in low:
            # "заверши сессию и запиши, что API готово" — what follows
            # the conjunction is the closing note. Without this the
            # sentence would close the session and lose its point.
            rest = low.split(word, 1)[1].strip()
            for lead in ("и запиши", "и заметка", "и отметь", "и добавь"):
                if rest.startswith(lead):
                    rest = rest[len(lead):].strip(" ,:")
                    break
            else:
                rest = rest.strip(" ,:")
            return "finish", rest

    for word in LAST_WORDS:
        if word in low:
            return "last", ""
    for word in CURRENT_WORDS:
        if word in low:
            return "current", ""

    for word in NOTE_WORDS:
        if low.startswith(word) or f" {word}" in low:
            return "note", low.split(word, 1)[1].strip(" ,:")

    for word in FOLDER_WORDS:
        if word in low:
            # The tail is taken from the **original**, not from the
            # normalised copy. Normalising is right for deciding which
            # phrase this is and fatal for what follows: it strips the
            # punctuation a path is made of: a Windows path came through as
            # `c proj rina` — a folder that does not exist, stored under
            # a name nobody can use.
            return "folder", _tail(text, word)

    for word in WORKED_WORDS:
        if word in low:
            return "worked", low.split(word, 1)[1].strip(" ,:")

    for word in START_WORDS:
        if low.startswith(word):
            # An empty goal is handed on as it is, for the same reason
            # as an empty thing to do: a phrase this stage refuses goes
            # on down the chain and ends in a web search for "начни
            # сессию". Saying "I did not catch what about" is the job of
            # whoever knows what was being asked.
            # The preposition stays. Russian declines, and Rina does
            # not: strip "над" from "начни сессию над протоколом" and
            # the goal is «протоколом», which comes back out of every
            # sentence in the wrong case — «Начала сессию
            # «протоколом»». Kept whole, the tail fits the frame the
            # person themselves used, and the frames below are written
            # so that it does.
            return "start", low[len(word):].strip(" ,:")
    return None


def _tail(text, word):
    """What follows a trigger word, in the person's own characters."""
    import re as _re

    found = _re.search(_re.escape(word).replace(r"\ ", r"\s+"),
                       text, _re.IGNORECASE)
    return text[found.end():].strip(" ,:") if found else ""


def _spell(seconds):
    """A stretch of time, as a person would say it."""
    seconds = max(0, int(seconds))
    hours, rest = divmod(seconds, 3600)
    minutes = rest // 60
    if hours and minutes:
        return tr("{h} ч {m} мин", h=hours, m=minutes)
    if hours:
        return tr("{h} ч", h=hours)
    if minutes:
        return tr("{m} мин", m=minutes)
    return tr("меньше минуты")


class SessionStore:
    """
    The sessions, in the settings store beside everything else that
    outlives a run.

    The store is handed in rather than taken: two cores in one process
    would otherwise share one list, and a check with a stand-in store
    would write into a person's real file — `4.0-B05` and `4.0-B06`.
    """

    #: How many finished sessions are kept.
    #:
    #: A bound rather than forever. This is a record of what somebody
    #: was doing, hour by hour; keeping it without end means the file
    #: grows for as long as the program is installed, and a person who
    #: switched watching on one afternoon two years ago has no idea what
    #: is in it. The oldest goes when the list is full, and the page
    #: says how many are kept.
    KEEP = 200

    def __init__(self, settings):
        self._settings = settings

    # ---- reading -------------------------------------------------------
    def all(self, open=None):
        """
        Every session, brought to the expected form.

        `open=True` is the one in progress, `False` the finished ones.
        A spoiled entry is dropped here rather than everywhere that
        shows the list: the file may have been edited by hand.
        """
        clean = []
        for item in (self._settings.get("sessions", []) or []):
            if not isinstance(item, dict):
                continue
            goal = str(item.get("goal", "")).strip()
            if not goal:
                continue
            finished = float(item.get("finished", 0) or 0)
            if open is not None and bool(finished) == open:
                continue
            apps = item.get("apps", {})
            clean.append({
                "id": str(item.get("id", "")) or uuid.uuid4().hex[:8],
                "goal": goal,
                "started": float(item.get("started", 0) or 0),
                "finished": finished,
                "focus": bool(item.get("focus", False)),
                "notes": [str(n) for n in (item.get("notes") or [])
                          if str(n).strip()],
                "commands": [str(c) for c in (item.get("commands") or [])
                             if str(c).strip()],
                "apps": {str(k): float(v) for k, v in apps.items()
                         if isinstance(apps, dict)},
                "folders": [str(f) for f in (item.get("folders") or [])
                            if str(f).strip()],
            })
        return clean

    def current(self):
        """The open session, or None. There is at most one."""
        open_ones = self.all(open=True)
        return open_ones[-1] if open_ones else None

    def last(self):
        """The most recently finished one, or None."""
        done = sorted(self.all(open=False), key=lambda s: s["finished"])
        return done[-1] if done else None

    def find(self, query):
        """Finished sessions whose goal contains what was named."""
        query = normalize(query or "")
        if not query:
            return []
        return [s for s in self.all() if query in normalize(s["goal"])]

    def spent(self, session, now=None):
        """How long a session has run — or has been running."""
        now = now if now is not None else time.time()
        end = session["finished"] or now
        return max(0.0, end - session["started"])

    def worked(self, query, since=None, now=None):
        """
        Total time on everything matching a name, over a period.

        `since` is a moment, not a number of days: "this week" is a
        decision about the calendar and belongs to whoever asks, not to
        the store.
        """
        now = now if now is not None else time.time()
        total = 0.0
        count = 0
        for one in self.find(query):
            if since is not None and (one["finished"] or now) < since:
                continue
            total += self.spent(one, now)
            count += 1
        return total, count

    # ---- writing -------------------------------------------------------
    def _save(self, items):
        self._settings.set("sessions", items)

    def _raw(self):
        rows = self._settings.get("sessions", []) or []
        return [r for r in rows if isinstance(r, dict)]

    def start(self, goal, focus=False):
        """
        Open a session. Returns it, or None if the goal was empty.

        Opening one while another is open is **refused** rather than
        resolved: closing the previous one quietly would end a stretch
        of work at a moment nobody chose, and the record would say it
        ended when the next one began. Whoever calls this asks first —
        `current()` says whether there is anything to ask about.
        """
        goal = (goal or "").strip()
        if not goal or self.current() is not None:
            return None
        item = {
            "id": uuid.uuid4().hex[:8],
            "goal": goal,
            "started": time.time(),
            "finished": 0.0,
            "focus": bool(focus),
            "notes": [],
            "commands": [],
            "apps": {},
            "folders": [],
        }
        rows = self._raw()
        rows.append(item)
        # Trimmed on opening rather than on closing: a person closing a
        # session should not have the act of closing throw an old one
        # away as a side effect.
        while len(rows) > self.KEEP:
            rows.pop(0)
        self._save(rows)
        return item

    def finish(self, note="", now=None):
        """Close the open session. Returns it as it ended, or None."""
        open_one = self.current()
        if open_one is None:
            return None
        rows = self._raw()
        for row in rows:
            if str(row.get("id", "")) != open_one["id"]:
                continue
            row["finished"] = now if now is not None else time.time()
            row["focus"] = False
            if (note or "").strip():
                row.setdefault("notes", []).append(note.strip())
            self._save(rows)
            break
        return next((s for s in self.all() if s["id"] == open_one["id"]), None)

    def note(self, text):
        """Add a note to the open session. Returns it, or None."""
        text = (text or "").strip()
        open_one = self.current()
        if not text or open_one is None:
            return None
        return self._touch(open_one["id"], lambda row:
                           row.setdefault("notes", []).append(text))

    def remember_command(self, text):
        """
        Note that a command was given while a session was open.

        Called for every command, and doing nothing when no session is
        open is the ordinary case rather than an error: the alternative
        is every caller asking first.
        """
        text = (text or "").strip()
        open_one = self.current()
        if not text or open_one is None:
            return None
        return self._touch(open_one["id"], lambda row:
                           row.setdefault("commands", []).append(text))

    def saw(self, app, seconds):
        """
        Add time spent in an application to the open session.

        Nothing happens without an open session, and nothing happens
        without the setting: the caller checks the setting, because the
        store must not be the place that decides whether a person
        agreed to be watched.
        """
        app = (app or "").strip()
        open_one = self.current()
        if not app or open_one is None or seconds <= 0:
            return None
        def add(row):
            apps = row.setdefault("apps", {})
            apps[app] = float(apps.get(app, 0)) + float(seconds)
        return self._touch(open_one["id"], add)

    def remember_folder(self, path):
        """A working folder, when the person has agreed to keep them."""
        path = (path or "").strip()
        open_one = self.current()
        if not path or open_one is None:
            return None
        def add(row):
            folders = row.setdefault("folders", [])
            if path not in folders:
                folders.append(path)
        return self._touch(open_one["id"], add)

    def set_focus(self, on):
        """Turn focus mode on or off for the open session (`4.0b-A05`)."""
        open_one = self.current()
        if open_one is None:
            return None
        return self._touch(open_one["id"],
                           lambda row: row.__setitem__("focus", bool(on)))

    def focused(self):
        """Is the open session a focused one."""
        open_one = self.current()
        return bool(open_one and open_one["focus"])

    def forget(self, session_id):
        """Drop one session. Used by "what Rina knows about me"."""
        rows = [r for r in self._raw()
                if str(r.get("id", "")) != str(session_id)]
        if len(rows) == len(self._raw()):
            return False
        self._save(rows)
        return True

    def _touch(self, session_id, change):
        rows = self._raw()
        for row in rows:
            if str(row.get("id", "")) == str(session_id):
                change(row)
                self._save(rows)
                return next((s for s in self.all()
                             if s["id"] == session_id), None)
        return None


# ---------------------------------------------------------------------------
# Saying it out loud
# ---------------------------------------------------------------------------
def say_started(session):
    return tr("Начала сессию {goal}.", goal=session["goal"])


def say_finished(session, spent):
    return tr("Сессия закрыта: {goal}, {spent}.",
              goal=session["goal"], spent=_spell(spent))


def say_session(session, spent, prefix=""):
    """
    A session read out: what it was about, how long, and what happened.

    The parts that are empty are left out rather than said as "notes:
    none". A list of absences is longer than the thing itself and tells
    a person nothing they did not know.
    """
    said = [prefix or tr("Сессия: {goal}, {spent}.",
                         goal=session["goal"], spent=_spell(spent))]
    if session["notes"]:
        said.append(tr("Заметки: {notes}.",
                       notes="; ".join(session["notes"][:5])))
    if session["commands"]:
        said.append(tr("Команд: {count}.", count=len(session["commands"])))
    if session["apps"]:
        top = sorted(session["apps"].items(), key=lambda kv: -kv[1])[:3]
        said.append(tr("Больше всего: {apps}.",
                       apps=", ".join("%s — %s" % (name, _spell(secs))
                                      for name, secs in top)))
    if session["folders"]:
        said.append(tr("Каталоги: {folders}.",
                       folders=", ".join(session["folders"][:3])))
    return " ".join(said)


def say_worked(query, total, count):
    if not count:
        return tr("Про это у меня ничего не записано: {query}.", query=query)
    return tr("{query}: {spent}, сессий {count}.",
              query=query, spent=_spell(total), count=count)
