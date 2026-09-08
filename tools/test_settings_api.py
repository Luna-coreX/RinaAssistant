# -*- coding: utf-8 -*-
"""
B06: the core gets its settings through an interface, not through a
singleton.

The point of the check: two cores with different settings behave
differently, and the user's file is not touched at all.
"""
import os
import sys

sys.path.insert(0, r"C:\DevStation\PCDev\DesktopApps\RinaAssistant")
sys.path.insert(0, r"C:\DevStation\PCDev\DesktopApps\RinaAssistant\tools")
os.chdir(r"C:\DevStation\PCDev\DesktopApps\RinaAssistant")

from core import logging_setup
logging_setup.setup()

from sandbox import neutralise
box = neutralise()

from core.engine import RinaEngine
from core.events import EventBus
from core.settings_api import MemorySettings, SettingsProvider, default_settings

fails = 0


def check(label, cond, detail=""):
    global fails
    if not cond:
        fails += 1
    print(("OK   " if cond else "FAIL "), label, detail)


print("=== интерфейс ===")
mem = MemorySettings()
check("MemorySettings удовлетворяет протоколу",
      isinstance(mem, SettingsProvider))
check("общее хранилище тоже удовлетворяет",
      isinstance(default_settings(), SettingsProvider))

check("значение по умолчанию читается",
      mem.get("wake_word") == "Рина", f"| {mem.get('wake_word')}")
mem.set("wake_word", "Мира")
check("значение записывается", mem.get("wake_word") == "Мира")
before = mem.saves
mem.save()
check("сохранение считается", mem.saves == before + 1)

with mem.transaction():
    mem.set("volume", 42)
check("транзакция работает", mem.get("volume") == 42)


def make(values):
    settings = MemorySettings(values)
    engine = RinaEngine(event_bus=EventBus(), settings=settings)
    engine._speak_blocking = lambda text: None
    said = []
    engine.say = lambda text, sound="response": said.append(text)
    return engine, settings, said


print()
print("=== разные настройки — разное поведение ===")
A, a_set, said_a = make({"web_search_fallback": True, "llm_enabled": False})
B, b_set, said_b = make({"web_search_fallback": False, "llm_enabled": False})

A.handle_command("столица австралии")
B.handle_command("столица австралии")
check("с запасным поиском — ищет",
      "поищу" in said_a[-1], f"| {said_a[-1]}")
check("без запасного поиска — отказ",
      "не поняла" in said_b[-1], f"| {said_b[-1]}")

print()
print("=== состояние не пересекается ===")
check("история пишется каждому своя",
      len(a_set.get("history")) == 1 and len(b_set.get("history")) == 1,
      f"| A={len(a_set.get('history'))}, B={len(b_set.get('history'))}")

A.handle_command("поставь таймер на 10 минут")
check("напоминание только у A",
      len(a_set.get("reminders")) == 1 and len(b_set.get("reminders")) == 0,
      f"| A={len(a_set.get('reminders'))}, B={len(b_set.get('reminders'))}")

print()
print("=== файл пользователя не тронут ===")
real = default_settings()
check("общее хранилище не использовалось ядрами",
      A._settings is not real and B._settings is not real)
check("слово активации в общем хранилище не менялось",
      real.get("wake_word") == "Рина", f"| {real.get('wake_word')}")

print()
print("=== по умолчанию — общее хранилище ===")
plain = RinaEngine(event_bus=EventBus())
check("без аргумента берётся общее хранилище",
      plain._settings is real)

print()
print("=== список целиком пишется под замком ===")

# «Прочитать — изменить — записать» без общего замка теряет чужую правку
# целиком, а не по ключу: второй поток пишет свой список поверх первого. У
# своих команд таких потока два — ввоз из файла и ответ Рины; у напоминаний
# тоже два — планировщик, помечающий сработавшее, и человек, заводящий
# новое.
import threading

from core.settings_api import MemorySettings
from voice.user_commands import UserCommandStore


class RaceSettings(MemorySettings):
    """
    Хранилище, на котором гонка происходит **обязательно**, а не иногда.

    Две предыдущие редакции этой проверки были негодными, и обе по одной
    причине: полагались на удачу планировщика. Первая запускала сорок
    потоков в цикле, и каждый успевал закончить до старта следующего.
    Вторая добавила барьер и задержку — и повела себя непристойно: на
    двадцати потоках из двадцати записей доживала одна, на сорока не
    терялось ничего. Проверка, зелёная через раз, хуже отсутствующей: ей
    перестают верить, а потом перестают верить и остальным.

    Здесь удачи нет. Потока два, и чтение не возвращается, пока не
    прочитал второй. Нет общего замка — оба увидят один и тот же список, и
    второй затрёт первого; всегда. Есть замок — второй до чтения не
    доберётся, встреча не состоится, ожидание истечёт по сроку и всё
    пройдёт как надо; тоже всегда.
    """

    def __init__(self, values, meeting):
        super().__init__(values)
        self._meeting = meeting

    def get(self, key, default=None):
        value = super().get(key, default)
        if key == "custom_commands":
            try:
                # Срок — для случая «замок на месте»: там встреча не
                # состоится никогда, и ждать её вечно значило бы повесить
                # проверку вместо того, чтобы её пройти.
                self._meeting.wait(timeout=1.0)
            except threading.BrokenBarrierError:
                pass
        return value


meeting = threading.Barrier(2)
shared = RaceSettings({"custom_commands": []}, meeting)
store = UserCommandStore(shared)


def add_one(number):
    # Транзакции здесь нет нарочно: её обязан держать сам `merge`, и весь
    # смысл проверки в этом. Оберни мы вызов снаружи — проверка прошла бы
    # и с прежним кодом, то есть согласилась бы со своим автором.
    store.merge([{"id": f"cmd_{number}", "type": "speak",
                  "triggers": [f"фраза {number}"], "enabled": False}],
                lambda n=number: f"cmd_{n}")


threads = [threading.Thread(target=add_one, args=(i,)) for i in (1, 2)]
for t in threads:
    t.start()
for t in threads:
    t.join()

survived = store.all()
check("запись не потеряна, когда двое пишут разом",
      len(survived) == 2, f"| дожило {len(survived)} из 2")
check("и номера не задвоились",
      len({c["id"] for c in survived}) == len(survived),
      f"| {len({c['id'] for c in survived})} разных из {len(survived)}")

print()
print("ИТОГО ошибок:", fails)

# `os._exit` нужен потому, что фоновые потоки ядра держат процесс живым.
# Но он не сбрасывает буферы, и до этой строки весь вывод проверки уходил
# в никуда: в регрессе она показывалась пустой строкой, и при провале
# нельзя было узнать, что именно провалилось.
sys.stdout.flush()
sys.stderr.flush()
os._exit(1 if fails else 0)
