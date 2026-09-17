"""
Timers, alarms and reminders.

Parses phrases of the form "поставь таймер на 10 минут", "напомни через
полчаса позвонить маме", "разбуди в 7:30" and keeps what is planned between
runs — a reminder must survive a restart of the application, or it cannot be
trusted.

Here there is only phrase parsing and the store. The core
(RinaEngine.start_reminders) checks the due time once a second in a
background thread: one shared poll is cheaper and more reliable than a
thread per reminder.
"""

import math
import re
import time
import uuid

from core.i18n import t as tr
from voice.textmatch import normalize


# ---------------------------------------------------------------------------
# Parsing phrases
# ---------------------------------------------------------------------------
TIMER_WORDS = ("таймер", "засеки", "засечь", "timer")
REMIND_WORDS = ("напомни", "напоминание", "напомнить", "remind")
ALARM_WORDS = ("разбуди", "будильник", "подъём", "подъем", "alarm")
LIST_WORDS = ("какие таймеры", "мои напоминания", "список напоминаний",
              "что запланировано", "какие напоминания", "мои таймеры")
CANCEL_WORDS = ("отмени таймер", "отмени напоминание", "отмени напоминания",
                "убери таймер", "убери напоминания", "отмени все таймеры",
                "удали напоминания", "сбрось таймер")

# Speech rarely gives digits — the numerals have to be understood as words.
NUM_WORDS = {
    "один": 1, "одну": 1, "одна": 1, "полторы": 1.5, "полтора": 1.5,
    "два": 2, "две": 2, "три": 3, "четыре": 4, "пять": 5, "шесть": 6,
    "семь": 7, "восемь": 8, "девять": 9, "десять": 10, "одиннадцать": 11,
    "двенадцать": 12, "тринадцать": 13, "четырнадцать": 14, "пятнадцать": 15,
    "шестнадцать": 16, "семнадцать": 17, "восемнадцать": 18,
    "девятнадцать": 19, "двадцать": 20, "тридцать": 30, "сорок": 40,
    "пятьдесят": 50, "шестьдесят": 60, "девяносто": 90,
}

#: "когда открою VS Code", "как открою студию", "при запуске блокнота".
#:
#: Only about a program being opened: a closed list of occasions (see
#: `TRIGGER_KINDS`) is a promise the code keeps. Widening it with words
#: before the shell can tell those apart would mean creating a reminder
#: that will never fire.
WHEN_APP = re.compile(
    r"[,\s]*(?:когда|как только|как|при)\s+"
    r"(?:я\s+)?(?:открою|открываю|запущу|запускаю|включу|"
    r"открытии|запуске|включении)\s+"
    # Everything after the verb is a **candidate**, not a name. The
    # condition is also put at the front of the phrase — "напомни, когда
    # открою студию, проверить почту" — and there is nothing here to draw
    # the boundary between the program and the thing to do. There is no
    # comma: `normalize` removes it before this point, and speech gives no
    # commas at all. The boundary is drawn by the router, from the index of
    # what is installed — knowledge the parsing does not have and should
    # not have.
    r"(?P<app>.+)$",
    re.IGNORECASE)

# More than a year ahead is almost certainly a recognition error
MAX_DELAY_SECONDS = 365 * 24 * 3600

UNIT_SECONDS = {
    "секунда": 1, "секунды": 1, "секунд": 1, "секунду": 1, "сек": 1,
    "second": 1, "seconds": 1,
    "минута": 60, "минуты": 60, "минут": 60, "минуту": 60, "мин": 60,
    "minute": 60, "minutes": 60,
    "час": 3600, "часа": 3600, "часов": 3600, "hour": 3600, "hours": 3600,
}


class Parsed:
    """What was recognised in the phrase."""

    def __init__(self, action, delay=None, at=None, text="", kind="timer",
                 when_app=""):
        self.action = action      # "create" | "list" | "cancel"
        self.delay = delay        # in how many seconds
        self.at = at              # an absolute time (timestamp)
        self.text = text          # what to remind about
        self.kind = kind          # "timer" | "reminder" | "alarm"
        #: The named program, if the reminder is bound to it rather than
        #: to a time (`4.0b-A03`). Here it is **the word that was said**:
        #: parsing a phrase does not know which programs are on the machine
        #: and must not — otherwise it stops being pure and cannot be
        #: checked without an index. The router resolves the word into a
        #: program.
        self.when_app = when_app


def _duration_seconds(text):
    """"10 минут", "полчаса", "пять секунд" -> seconds (or None)."""
    if re.search(r"\bполчаса\b", text):
        return 1800
    if re.search(r"\bполтора часа\b", text):
        return 5400

    # A number (in digits or in words) plus a unit. We add up ALL the pairs
    # rather than only the first: "1 час 30 минут" is an hour and a half,
    # and the user used to find out about the mistake an hour later.
    pattern = r"(\d+(?:[.,]\d+)?|[а-яё]+)\s*(" + "|".join(UNIT_SECONDS) + r")\b"
    seconds = 0.0
    found = False
    for match in re.finditer(pattern, text):
        raw, unit = match.group(1), match.group(2)
        try:
            amount = float(raw.replace(",", "."))
        except ValueError:
            amount = NUM_WORDS.get(raw)
            if amount is None:
                # "через час", "на минуту" — the numeral is omitted
                amount = 1
        seconds += amount * UNIT_SECONDS[unit]
        found = True

    if not found:
        return None
    # a very long number gives inf, and int(inf) is an exception. We also cut
    # off meaningless spans: "через 99999999 минут" is not a reminder.
    if not math.isfinite(seconds) or seconds <= 0:
        return None
    return int(min(seconds, MAX_DELAY_SECONDS))


def _absolute_time(text):
    """"в 15:00", "в 7 30", "в 9 утра" -> the nearest such moment (a timestamp)."""
    # "в 15:00" and "на 8 утра". The negative lookahead prevents confusion
    # with a duration: "на 10 минут" is a timer, not the time 10:00.
    match = re.search(
        r"\b(?:в|на)\s+(\d{1,2})(?:[:.\s](\d{2}))?\b"
        r"(?!\s*(?:секунд|минут|час|сек|мин))", text)
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    if hour > 23 or minute > 59:
        return None

    # "в 7 вечера" -> 19:00
    if re.search(r"\bвечера\b", text) and hour < 12:
        hour += 12
    if re.search(r"\bночи\b", text) and hour == 12:
        hour = 0

    now = time.localtime()
    target = time.struct_time((now.tm_year, now.tm_mon, now.tm_mday,
                               hour, minute, 0, 0, 0, -1))
    stamp = time.mktime(target)
    if stamp <= time.time():
        stamp += 24 * 3600          # the time has passed, so tomorrow
    if re.search(r"\bзавтра\b", text):
        stamp += 24 * 3600
    return stamp


def _reminder_text(text):
    """What exactly to remind about: the tail of the phrase after the time."""
    cleaned = re.sub(r"^.*?(напомни(?:ть)?|напоминание)\s*", "", text)
    # we cut off the time: "через 15 минут", "через час", "завтра в 9", "в 15:00"
    cleaned = re.sub(
        r"^(?:завтра|сегодня)?\s*"
        r"(через\s+.*?(?:секунд\w*|минут\w*|час\w*|полчаса)"
        r"|(?:в|на)\s+\d{1,2}(?:[:.\s]\d{2})?)\s*", "", cleaned)
    cleaned = re.sub(r"^(что|чтобы|о том|про то)\s+", "", cleaned)
    cleaned = re.sub(r"\b(завтра|утра|вечера|ночи)\b", "", cleaned)
    return cleaned.strip(" ,.—-")


def asked_for_one(text) -> bool:
    """
    Was this a request about time at all — whatever came of parsing it.

    Needed apart from `parse`, which answers "did it come out". The two
    differ exactly where it matters: "напомни позвонить маме" is a
    request with no time in it, and treating the failure to parse as
    "not about reminders" sent the phrase off to a web search.
    """
    low = normalize(text or "")
    if not low:
        return False
    # **Only at the front of the phrase.** A request begins with the
    # asking: "напомни позвонить маме", "поставь будильник". The same
    # words further in belong to a sentence about them — "что такое
    # напоминание в психологии" is a question, and answering it with
    # "Не поняла, когда напомнить" is a worse failure than the search
    # this was written to prevent.
    head = low.split()[:2]
    return any(word in head for word in
               TIMER_WORDS + REMIND_WORDS + ALARM_WORDS)


def parse(text):
    """Recognises a command about time. Returns Parsed or None."""
    if not text:
        return None
    low = normalize(text)
    if not low:
        return None

    if any(phrase in low for phrase in LIST_WORDS):
        return Parsed("list")
    if any(phrase in low for phrase in CANCEL_WORDS):
        return Parsed("cancel")

    is_timer = any(w in low for w in TIMER_WORDS)
    is_remind = any(w in low for w in REMIND_WORDS)
    is_alarm = any(w in low for w in ALARM_WORDS)
    if not (is_timer or is_remind or is_alarm):
        return None

    # The occasion is parsed **before** the time and cut off the phrase:
    # otherwise "когда открою студию" would stay in the reminder's text,
    # and the person would hear their own condition read back to them
    # instead of the thing to do.
    when = WHEN_APP.search(low)
    when_app = ""
    if when:
        when_app = when.group("app").strip(" ,.?!«»\"'")
        low = low[:when.start()].strip(" ,")

    delay = _duration_seconds(low)
    at = _absolute_time(low)
    if delay is None and at is None and not when_app:
        return None

    if is_alarm:
        kind = "alarm"
    elif is_remind:
        kind = "reminder"
    else:
        kind = "timer"

    label = _reminder_text(low) if is_remind else ""
    # absolute time has priority: "напомни в 15:00" is not "через 15"
    if at is not None and (is_alarm or is_remind or not is_timer):
        delay = None
    # The occasion beats the clock: "напомни через час, когда открою
    # студию" is a phrase in which the person contradicts themselves, and
    # one of the two has to be picked. What was named last is picked,
    # because that is the qualification.
    if when_app:
        delay = at = None
    return Parsed("create", delay=delay, at=at, text=label, kind=kind,
                  when_app=when_app)


# ---------------------------------------------------------------------------
# The store
# ---------------------------------------------------------------------------
#: The occasions Rina can wait for (`4.0b-A03`).
#:
#: The list is closed and lies next to the parsing: an occasion that is not
#: here is not stored. Otherwise an entry saying "waiting for event X"
#: would outlive the version in which X meant something, and would go on
#: waiting for ever — silently, because a reminder that did not fire shows
#: nothing of itself.
TRIGGER_KINDS = ("app.foreground",)


def clean_trigger(on):
    """
    An occasion -> a dict brought to the expected form, or None.

    One door for both the store and the comparison: different reading rules
    in two places are a way to create a reminder that will never fire and
    never find out about it.
    """
    if not isinstance(on, dict):
        return None
    kind = str(on.get("kind") or "")
    launch = str(on.get("launch") or "")
    if kind not in TRIGGER_KINDS or not launch:
        return None
    return {"kind": kind, "launch": launch,
            "app": str(on.get("app") or "")}


def _same_trigger(saved, want):
    """
    The same occasion.

    The path is compared case-insensitively: Windows does not tell
    `Code.exe` from `code.exe`, and the shell takes the path from the
    window rather than from our index — so it may return any spelling.
    """
    return (saved.get("kind") == want.get("kind")
            and saved.get("launch", "").casefold()
            == want.get("launch", "").casefold())


class ReminderStore:
    """What is planned, surviving a restart of the application."""

    def __init__(self, settings):
        self._settings = settings

    def all(self):
        """What is planned, brought to the expected form (see HistoryStore.all)."""
        clean = []
        for item in (self._settings.get("reminders", []) or []):
            if not isinstance(item, dict) or not item.get("id"):
                continue
            on = clean_trigger(item.get("on"))
            try:
                fire_at = float(item.get("fire_at", 0) or 0)
            except (TypeError, ValueError):
                fire_at = 0.0
            # A reminder has to know when to fire: by the clock or by an
            # event. With neither there is nothing to wait for, and such an
            # entry is rubbish that survived until it was read.
            #
            # "No clock" used to mean "throw away", and that was right
            # while no other occasions existed. It is wrong now: an entry
            # bound to an event has no clock by construction, and the old
            # rule would have swept it away silently.
            if not fire_at and on is None:
                continue
            clean.append({
                "id": str(item["id"]),
                "kind": str(item.get("kind", "reminder")),
                "text": str(item.get("text", "")),
                "fire_at": fire_at,
                "on": on,
                "created_at": item.get("created_at", 0),
                "done": bool(item.get("done")),
            })
        return clean

    def active(self):
        return [r for r in self.all() if not r.get("done")]

    def save_all(self, items):
        """
        Write the list as a whole — under a transaction.

        Both the scheduler marking what has fired and the person creating
        something new come here: two threads, one write. The same rule as
        for the user's own commands.
        """
        with self._settings.transaction():
            self._settings.set("reminders", items)
            self._settings.save()

    MAX_FUTURE = 10 * 365 * 24 * 3600      # beyond ten years is knowingly a mistake

    def add(self, kind, fire_at, text="", on=None):
        on = clean_trigger(on)
        if on is not None:
            # Something bound to an event has no clock at all, rather
            # than a "zero": `fire_at = 0` is in the past, and the
            # scheduler would consider such a reminder fifty years
            # overdue.
            fire_at = 0.0
        else:
            try:
                fire_at = float(fire_at)
            except (TypeError, ValueError):
                fire_at = time.time()
            fire_at = min(fire_at, time.time() + self.MAX_FUTURE)
        item = {
            "id": "rem_" + uuid.uuid4().hex[:6],
            "kind": kind,
            "text": text,
            "fire_at": float(fire_at),
            "on": on,
            "created_at": time.time(),
            "done": False,
        }
        # reading and writing in one operation: the scheduler in a
        # background thread marks what has fired at exactly the moment the
        # user adds something new, and without a lock one overwrites the
        # other
        with self._settings.transaction():
            items = self.all()
            items.append(item)
            self.save_all(items)
        return item

    def mark_done(self, item_id):
        with self._settings.transaction():
            items = self.all()
            for item in items:
                if item.get("id") == item_id:
                    item["done"] = True
            self.save_all(items)

    def remove(self, item_id):
        with self._settings.transaction():
            self.save_all([r for r in self.all() if r.get("id") != item_id])

    def clear_active(self):
        with self._settings.transaction():
            removed = len(self.active())
            self.save_all([r for r in self.all() if r.get("done")])
        return removed

    def due(self, now=None):
        now = now or time.time()
        return [r for r in self.active()
                if r.get("on") is None and r.get("fire_at", 0) <= now]

    def triggered(self, event):
        """
        What is waiting for this event (`4.0b-A03`).

        Matched by the launch path, not by name. A person says the name
        however it comes out — "код", "вээс код", "студия" — and comparing
        what was said with what the shell sees in a window would mean
        guessing twice. The path is resolved once, at the moment the
        reminder is created, by the same index as a launch: after that the
        comparison is exact.
        """
        want = clean_trigger(event)
        if want is None:
            return []
        return [r for r in self.active()
                if r.get("on") and _same_trigger(r["on"], want)]


# The scheduler lives in the core (core/engine.py): here there is only
# phrase parsing, the store and the wordings — the module does not depend on
# the interface.

# ---------------------------------------------------------------------------
# The wordings
# ---------------------------------------------------------------------------
def humanize_left(seconds):
    """"через 1 ч 5 мин" — how much is left."""
    seconds = max(0, int(seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return tr("{h} ч {m} мин", h=hours, m=minutes)
    if minutes:
        return tr("{m} мин {s} с", m=minutes, s=secs)
    return tr("{s} с", s=secs)


def when_text(fire_at):
    """The firing time in a readable form."""
    try:
        stamp = time.localtime(fire_at)
    except (OSError, OverflowError, ValueError):
        # a date outside a sensible range: the string has to be shown all
        # the same, or one such entry would wreck the whole tab and it could
        # not be removed
        return "—"
    today = time.localtime()
    clock = time.strftime("%H:%M", stamp)
    if (stamp.tm_year, stamp.tm_mon, stamp.tm_mday) == \
            (today.tm_year, today.tm_mon, today.tm_mday):
        return clock
    return time.strftime("%d.%m %H:%M", stamp)


def describe(item):
    """A line for the list: "Таймер — 14:30 (через 5 мин)"."""
    titles = {"timer": tr("Таймер"), "reminder": tr("Напоминание"),
              "alarm": tr("Будильник")}
    title = titles.get(item.get("kind"), tr("Напоминание"))
    if item.get("text"):
        title = f"{title}: {item['text']}"
    left = humanize_left(item.get("fire_at", 0) - time.time())
    return f"{title} — {when_text(item.get('fire_at', 0))} ({left})"
