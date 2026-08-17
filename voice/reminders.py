"""
Таймеры, будильники и напоминания.

Разбирает фразы вида «поставь таймер на 10 минут», «напомни через полчаса
позвонить маме», «разбуди в 7:30» и хранит запланированное между запусками —
напоминание должно пережить перезапуск приложения, иначе ему нельзя доверять.

Планировщик (Scheduler) живёт в GUI-потоке на QTimer: проверять раз в секунду
дешевле и надёжнее, чем держать поток на каждое напоминание.
"""

import re
import time
import uuid

from PySide6.QtCore import QObject, QTimer, Signal

from core.i18n import t as tr
from voice.textmatch import normalize


# ---------------------------------------------------------------------------
# Разбор фраз
# ---------------------------------------------------------------------------
TIMER_WORDS = ("таймер", "засеки", "засечь", "timer")
REMIND_WORDS = ("напомни", "напоминание", "напомнить", "remind")
ALARM_WORDS = ("разбуди", "будильник", "подъём", "подъем", "alarm")
LIST_WORDS = ("какие таймеры", "мои напоминания", "список напоминаний",
              "что запланировано", "какие напоминания", "мои таймеры")
CANCEL_WORDS = ("отмени таймер", "отмени напоминание", "отмени напоминания",
                "убери таймер", "убери напоминания", "отмени все таймеры",
                "удали напоминания", "сбрось таймер")

# Речь редко даёт цифры — числительные приходится понимать словами.
NUM_WORDS = {
    "один": 1, "одну": 1, "одна": 1, "полторы": 1.5, "полтора": 1.5,
    "два": 2, "две": 2, "три": 3, "четыре": 4, "пять": 5, "шесть": 6,
    "семь": 7, "восемь": 8, "девять": 9, "десять": 10, "одиннадцать": 11,
    "двенадцать": 12, "тринадцать": 13, "четырнадцать": 14, "пятнадцать": 15,
    "шестнадцать": 16, "семнадцать": 17, "восемнадцать": 18,
    "девятнадцать": 19, "двадцать": 20, "тридцать": 30, "сорок": 40,
    "пятьдесят": 50, "шестьдесят": 60, "девяносто": 90,
}

UNIT_SECONDS = {
    "секунда": 1, "секунды": 1, "секунд": 1, "секунду": 1, "сек": 1,
    "second": 1, "seconds": 1,
    "минута": 60, "минуты": 60, "минут": 60, "минуту": 60, "мин": 60,
    "minute": 60, "minutes": 60,
    "час": 3600, "часа": 3600, "часов": 3600, "hour": 3600, "hours": 3600,
}


class Parsed:
    """Что распознали во фразе."""

    def __init__(self, action, delay=None, at=None, text="", kind="timer"):
        self.action = action      # "create" | "list" | "cancel"
        self.delay = delay        # через сколько секунд
        self.at = at              # абсолютное время (timestamp)
        self.text = text          # о чём напомнить
        self.kind = kind          # "timer" | "reminder" | "alarm"


def _duration_seconds(text):
    """«10 минут», «полчаса», «пять секунд» -> секунды (или None)."""
    if re.search(r"\bполчаса\b", text):
        return 1800
    if re.search(r"\bполтора часа\b", text):
        return 5400

    # число (цифрами или словом) + единица
    pattern = r"(\d+(?:[.,]\d+)?|[а-яё]+)\s*(" + "|".join(UNIT_SECONDS) + r")\b"
    match = re.search(pattern, text)
    if not match:
        return None

    raw, unit = match.group(1), match.group(2)
    try:
        amount = float(raw.replace(",", "."))
    except ValueError:
        amount = NUM_WORDS.get(raw)
        if amount is None:
            # «через час», «на минуту» — числительное опущено
            amount = 1
    return int(amount * UNIT_SECONDS[unit])


def _absolute_time(text):
    """«в 15:00», «в 7 30», «в 9 утра» -> ближайший такой момент (timestamp)."""
    # «в 15:00» и «на 8 утра». Отрицательный просмотр вперёд не даёт спутать
    # с длительностью: «на 10 минут» — это таймер, а не время 10:00.
    match = re.search(
        r"\b(?:в|на)\s+(\d{1,2})(?:[:.\s](\d{2}))?\b"
        r"(?!\s*(?:секунд|минут|час|сек|мин))", text)
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    if hour > 23 or minute > 59:
        return None

    # «в 7 вечера» -> 19:00
    if re.search(r"\bвечера\b", text) and hour < 12:
        hour += 12
    if re.search(r"\bночи\b", text) and hour == 12:
        hour = 0

    now = time.localtime()
    target = time.struct_time((now.tm_year, now.tm_mon, now.tm_mday,
                               hour, minute, 0, 0, 0, -1))
    stamp = time.mktime(target)
    if stamp <= time.time():
        stamp += 24 * 3600          # время уже прошло — значит, завтра
    if re.search(r"\bзавтра\b", text):
        stamp += 24 * 3600
    return stamp


def _reminder_text(text):
    """Что именно напомнить: хвост фразы после времени."""
    cleaned = re.sub(r"^.*?(напомни(?:ть)?|напоминание)\s*", "", text)
    # отрезаем время: «через 15 минут», «через час», «завтра в 9», «в 15:00»
    cleaned = re.sub(
        r"^(?:завтра|сегодня)?\s*"
        r"(через\s+.*?(?:секунд\w*|минут\w*|час\w*|полчаса)"
        r"|(?:в|на)\s+\d{1,2}(?:[:.\s]\d{2})?)\s*", "", cleaned)
    cleaned = re.sub(r"^(что|чтобы|о том|про то)\s+", "", cleaned)
    cleaned = re.sub(r"\b(завтра|утра|вечера|ночи)\b", "", cleaned)
    return cleaned.strip(" ,.—-")


def parse(text):
    """Распознаёт команду про время. Возвращает Parsed или None."""
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

    delay = _duration_seconds(low)
    at = _absolute_time(low)
    if delay is None and at is None:
        return None

    if is_alarm:
        kind = "alarm"
    elif is_remind:
        kind = "reminder"
    else:
        kind = "timer"

    label = _reminder_text(low) if is_remind else ""
    # у абсолютного времени приоритет: «напомни в 15:00» — это не «через 15»
    if at is not None and (is_alarm or is_remind or not is_timer):
        delay = None
    return Parsed("create", delay=delay, at=at, text=label, kind=kind)


# ---------------------------------------------------------------------------
# Хранилище
# ---------------------------------------------------------------------------
class ReminderStore:
    """Запланированное, переживающее перезапуск приложения."""

    def __init__(self, settings):
        self._settings = settings

    def all(self):
        return list(self._settings.get("reminders", []) or [])

    def active(self):
        return [r for r in self.all() if not r.get("done")]

    def save_all(self, items):
        self._settings.set("reminders", items)
        self._settings.save()

    def add(self, kind, fire_at, text=""):
        item = {
            "id": "rem_" + uuid.uuid4().hex[:6],
            "kind": kind,
            "text": text,
            "fire_at": float(fire_at),
            "created_at": time.time(),
            "done": False,
        }
        items = self.all()
        items.append(item)
        self.save_all(items)
        return item

    def mark_done(self, item_id):
        items = self.all()
        for item in items:
            if item.get("id") == item_id:
                item["done"] = True
        self.save_all(items)

    def remove(self, item_id):
        self.save_all([r for r in self.all() if r.get("id") != item_id])

    def clear_active(self):
        removed = len(self.active())
        self.save_all([r for r in self.all() if r.get("done")])
        return removed

    def due(self, now=None):
        now = now or time.time()
        return [r for r in self.active() if r.get("fire_at", 0) <= now]


# ---------------------------------------------------------------------------
# Планировщик
# ---------------------------------------------------------------------------
class Scheduler(QObject):
    """Раз в секунду проверяет, не пора ли что-то напомнить."""

    fired = Signal(dict)          # сработавшее напоминание

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.store = ReminderStore(settings)
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)

    def start(self):
        self._timer.start()

    def stop(self):
        self._timer.stop()

    def _tick(self):
        for item in self.store.due():
            self.store.mark_done(item["id"])
            self.fired.emit(item)


# ---------------------------------------------------------------------------
# Формулировки
# ---------------------------------------------------------------------------
def humanize_left(seconds):
    """«через 1 ч 5 мин» — сколько осталось."""
    seconds = max(0, int(seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return tr("{h} ч {m} мин", h=hours, m=minutes)
    if minutes:
        return tr("{m} мин {s} с", m=minutes, s=secs)
    return tr("{s} с", s=secs)


def when_text(fire_at):
    """Время срабатывания в читаемом виде."""
    stamp = time.localtime(fire_at)
    today = time.localtime()
    clock = time.strftime("%H:%M", stamp)
    if (stamp.tm_year, stamp.tm_mon, stamp.tm_mday) == \
            (today.tm_year, today.tm_mon, today.tm_mday):
        return clock
    return time.strftime("%d.%m %H:%M", stamp)


def describe(item):
    """Строка для списка: «Таймер — 14:30 (через 5 мин)»."""
    titles = {"timer": tr("Таймер"), "reminder": tr("Напоминание"),
              "alarm": tr("Будильник")}
    title = titles.get(item.get("kind"), tr("Напоминание"))
    if item.get("text"):
        title = f"{title}: {item['text']}"
    left = humanize_left(item.get("fire_at", 0) - time.time())
    return f"{title} — {when_text(item.get('fire_at', 0))} ({left})"
