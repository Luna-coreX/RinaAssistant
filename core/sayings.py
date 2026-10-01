"""
Several ways to say one thing.

Asked for by a person (2026-10-02): Rina answered «Дел нет» the same way
every time, and the same words on the tenth day stop sounding like
somebody and start sounding like a table. So each common answer has a few
variants, and the one said is picked at random — never the one said last
time for the same thing.

**The first variant is the plain one**, and it is the one the checks hear.
A recorded utterance, a golden case or an exact assertion is about what Rina
decided, not which of her words she happened to pick; with
`RINA_PLAIN_SPEECH=1` in the environment every answer is its first variant.
`tools/console.py` sets it for every check, and `tools/test_sayings.py`
switches it off to check the variety itself.

Every variant is a key of the translation table, like any other line Rina
says (`tools/check_core_strings.py` reads this table), and all variants of
one saying take the same values.
"""
import os
import random
import threading

from core.i18n import t as tr

SAYINGS = {
    # --- things to do ---
    "todo.none": ("Дел нет.", "Список дел пуст.", "Пусто — ни одного дела.",
                  "Дел пока нет — можно выдохнуть."),
    "todo.one": ("Одно дело: {text}.", "Есть одно дело: {text}.",
                 "Всего одно: {text}."),
    "todo.many": ("Дел {count}: {listed}.", "В списке дел — {count}: {listed}.",
                  "Ждут своей очереди {count}: {listed}."),
    "todo.many_first": ("Дел {count}, первые пять: {listed}.",
                        "Дел {count}, вот первые пять: {listed}."),
    "todo.added": ("Записала: {text}.", "Добавила в дела: {text}.",
                   "Готово, в списке: {text}.", "Записала, не забудем: {text}."),
    "todo.closed": ("Готово: {text}.", "Отметила: {text}.",
                    "Вычеркнула: {text}."),

    # --- reminders and timers ---
    "reminders.none": ("Ничего не запланировано.",
                       "Пока ничего не запланировано.",
                       "Напоминаний нет — всё спокойно."),
    "reminders.cancelled": ("Отменила: {count}.", "Сняла с плана: {count}."),
    "reminders.nothing": ("Нечего отменять.", "Отменять нечего — ничего не стоит."),
    "timer.set": ("Засекла {left}.", "Хорошо, {left}. Засекаю.",
                  "Поставила таймер на {left}.", "Таймер на {left} пошёл."),
    "reminder.in": ("Напомню через {left}: {text}.",
                    "Хорошо, через {left} напомню: {text}.",
                    "Через {left} скажу: {text}."),
    "reminder.at": ("Напомню в {time}: {text}.", "В {time} напомню: {text}.",
                    "Хорошо, в {time} скажу: {text}."),
    "alarm.at": ("Разбужу в {time}.", "Хорошо, разбужу в {time}.",
                 "Будильник на {time} поставила."),

    # --- the clock ---
    "clock.time": ("Сейчас {time}.", "На часах {time}.", "Уже {time}."),
    "clock.date": ("Сегодня {day} {month}, {weekday}.",
                   "Сегодня {weekday}, {day} {month}.",
                   "{day} {month}, {weekday}."),
    "clock.weekday": ("Сегодня {weekday}.", "Сегодня у нас {weekday}.",
                      "Сегодня — {weekday}."),

    # --- the machine ---
    "system.volume_up": ("Прибавила громкость.", "Сделала погромче.", "Громче."),
    "system.volume_down": ("Убавила громкость.", "Сделала потише.", "Тише."),
    "system.media_next": ("Следующий трек.", "Дальше.",
                          "Переключила на следующий."),
    "system.media_prev": ("Предыдущий трек.", "Вернула предыдущий."),
    "brightness.up": ("Сделала ярче.", "Прибавила яркость.", "Ярче."),
    "brightness.down": ("Сделала темнее.", "Убавила яркость.", "Темнее."),
    "brightness.level": ("Яркость {level}%.", "Поставила яркость {level}%.",
                         "Готово, яркость {level}%."),

    # --- answers ---
    "calc": ("Получается {result}.", "Будет {result}.", "Выходит {result}."),
    "cancelled": ("Хорошо, отменяю.", "Ладно, не буду.", "Отменила."),
    "wake": ("Да? Слушаю.", "Слушаю.", "Я тут."),
    "answer.hello": ("Привет. Слушаю.", "Привет! Чем помочь?", "Привет. Я тут."),
    "answer.thanks": ("Всегда рада помочь.", "Обращайся.", "Рада помочь."),
    "answer.bye": ("До встречи.", "Пока! До связи.", "До скорого."),
    "answer.how_are_you": ("У меня всё ровно. Чем помочь?",
                           "Всё хорошо, спасибо. Чем займёмся?",
                           "Нормально, работаю. Что нужно?"),

    # --- a person's own commands, when the card says nothing ---
    "command.app": ("Запускаю программу.", "Открываю программу.", "Запускаю."),
    "command.folder": ("Открываю папку.", "Сейчас открою папку."),
    "command.website": ("Открываю сайт.", "Сейчас открою сайт."),
    "command.done": ("Готово.", "Сделала.", "Есть, готово."),
}

#: The variant said last for each saying.
_last = {}
_lock = threading.Lock()

#: Set by a check to decide for itself: None means "ask the environment".
PLAIN = None


def _plain():
    if PLAIN is not None:
        return PLAIN
    return os.environ.get("RINA_PLAIN_SPEECH") == "1"


def say(key, **values):
    """
    One of the ways to say `key`, translated and filled in.

    Never the same variant twice in a row for the same saying: two equal
    answers one after the other is exactly the table-feeling this exists to
    remove.
    """
    variants = SAYINGS[key]
    if _plain() or len(variants) == 1:
        chosen = variants[0]
    else:
        with _lock:
            last = _last.get(key)
            chosen = random.choice([v for v in variants if v != last])
            _last[key] = chosen
    return tr(chosen, **values)
