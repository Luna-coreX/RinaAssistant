"""
The time, the date and the day of the week (`4.0b-K03`).

Until 4.0b-K03 Rina knew the time only through the "Часы" example plugin,
and plugins are off on a fresh install (`enabled_plugins: []`). So on a
clean machine "который час" did not work, although the shell's own input
hint suggests exactly that phrase as the first thing to try.

The parse is a pure function, the same split as the calculator: the router
needs an intent, and the answer is assembled by the tool. The values the
tool returns are also what the constructor's "find out" step will read
(`4.0b-K02`), so they are kept separate from the sentence they are said in.
"""

import re
from datetime import datetime

from core.i18n import t as tr
# `say` is this module's own function below; the catalogue's is `saying`.
from core.sayings import say as saying


#: Month names in the genitive, as a date is said: «1 октября».
#:
#: A table rather than `strftime("%B")`, for the same reason as in
#: `core/llm.py`: that answers in the machine's locale, and the locale of
#: the machine is not the language Rina was asked to speak.
MONTHS = ("января", "февраля", "марта", "апреля", "мая", "июня", "июля",
          "августа", "сентября", "октября", "ноября", "декабря")

#: Monday first, matching `datetime.weekday()`.
WEEKDAYS = ("понедельник", "вторник", "среда", "четверг", "пятница",
            "суббота", "воскресенье")

#: What a question asks about -> the ways of asking it, with the filler
#: words already removed (see `FILLER`).
#:
#: **Whole phrases, not words found inside a phrase.** «сколько времени»
#: is also the start of «сколько времени ушло на отчёт» (sessions) and of
#: «сколько времени до отпуска», which is not a question about the clock.
#: A phrase that says more than the question is left to the stages that
#: understand the rest, or to the model.
PHRASES = {
    "time": ("который час", "сколько времени", "сколько время",
             "время", "текущее время", "точное время",
             "what time is it", "what is the time", "the time", "time",
             "current time"),
    "date": ("какое число", "какое число месяца", "какая дата", "дата",
             "какой день", "какой день месяца", "какое число какой день",
             "what is the date", "what date is it", "the date", "date",
             "what is the date today", "what day is it"),
    "weekday": ("какой день недели", "день недели",
                "what day of the week is it", "what is the day of the week"),
}

#: Words that change nothing about the question.
#:
#: «сейчас» and «сегодня» are here on purpose: «который сейчас час» and
#: «какое сегодня число» are the same questions as without them, and
#: without stripping them every question would need each of its forms
#: listed by hand.
FILLER = frozenset({
    "а", "ну", "слушай", "скажи", "подскажи", "мне",
    "пожалуйста", "не", "знаешь", "сейчас", "сегодня", "у", "нас",
    "please", "tell", "me", "now", "today", "can", "you", "hey",
})

_LOOKUP = {phrase: what for what, phrases in PHRASES.items()
           for phrase in phrases}


def _normalize(text):
    low = str(text or "").lower().replace("ё", "е").replace("’", "'")
    # «what's» is «what is» once the apostrophe is gone.
    low = low.replace("what's", "what is")
    words = re.findall(r"[\w]+", low)
    return " ".join(w for w in words if w not in FILLER)


def classify(text):
    """What the phrase asks: "time", "date", "weekday" — or None."""
    return _LOOKUP.get(_normalize(text))


def values(now=None):
    """
    Today's values, each ready to be put into a sentence.

    `now` is taken from outside so the checks do not depend on the hour
    they happen to run at.
    """
    now = now or datetime.now()
    return {
        # «9:05», not «09:05»: the leading zero is how a clock face
        # reads, and a voice reading it out says "ноль девять".
        "time": f"{now.hour}:{now.minute:02d}",
        "day": now.day,
        "month": tr(MONTHS[now.month - 1]),
        "weekday": tr(WEEKDAYS[now.weekday()]),
        "year": now.year,
        "iso": now.date().isoformat(),
    }


def value(what, now=None):
    """The bare value one question asks for: «четверг», «9:05», «1 октября»."""
    v = values(now)
    if what == "date":
        return f"{v['day']} {v['month']}"
    if what == "weekday":
        return v["weekday"]
    return v["time"]


def say(what, now=None):
    """The sentence for one question."""
    v = values(now)
    if what == "date":
        return saying("clock.date", **v)
    if what == "weekday":
        return saying("clock.weekday", **v)
    return saying("clock.time", **v)
