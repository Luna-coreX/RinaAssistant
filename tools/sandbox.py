# -*- coding: utf-8 -*-
"""
Песочница для тестов: обезвреживает ВСЕ побочные эффекты разом.

Появилась после того, как тест двух ядер подменил звук, системные действия и
запуск программ — и забыл браузер. Фраза, не разобранная конвейером, уходит в
запасной веб-поиск, и на машине разработчика открылись настоящие вкладки.

Перечислять подмены в каждом тесте вручную — значит однажды снова забыть одну.
Здесь они собраны в одном месте, и это то же место, где ведётся каталог
побочных эффектов из docs/INVENTORY-3.1.0.md, §3.

    from tools.sandbox import neutralise
    box = neutralise()          # всё обезврежено
    ...
    box.launched, box.actions, box.opened, box.spoken
"""

import sys


class Recorded:
    """Что было бы сделано, если бы не песочница."""

    def __init__(self):
        self.launched = []      # запущенные программы
        self.actions = []       # системные действия
        self.opened = []        # открытые ссылки
        self.paths = []         # открытые файлы и папки
        self.spoken = []        # произнесённое
        self.reminders = []     # заведённые напоминания

    def clear(self):
        for name in vars(self):
            getattr(self, name).clear()


def neutralise(record=None):
    """
    Подменяет всё, что меняет мир. Возвращает Recorded.

    Список намеренно исчерпывающий: лучше подменить лишнее, чем однажды
    открыть пользователю браузер из теста.
    """
    box = record or Recorded()

    # --- звук ---
    from voice import sounds
    sounds.play_response = lambda s: None
    sounds.play_error = lambda s: None
    sounds.play_activation = lambda s: None

    # --- запуск программ ---
    from voice import app_index
    app_index.launch = lambda entry: (box.launched.append(entry.name), True)[1]

    # --- системные действия ---
    from voice import system_control
    for key in list(system_control.RUNNERS):
        system_control.RUNNERS[key] = (
            lambda k: (lambda: (box.actions.append(k), True)[1]))(key)

    # --- браузер: и явный поиск, и запасной ---
    from voice import websearch
    websearch.webbrowser.open = lambda url, *a, **k: (
        box.opened.append(url), True)[1]

    # --- открытие файлов и папок пользовательскими командами ---
    from voice import user_commands
    user_commands._open_path = lambda path: (box.paths.append(path), True)[1]

    # --- озвучка ---
    from voice import tts
    tts._play_audio_file = lambda path, delete_after=False: True

    # --- сеть к языковой модели ---
    from core import llm
    llm.ask = lambda question, history=None: (_ for _ in ()).throw(
        llm.LLMError("модель в песочнице недоступна"))

    # --- напоминания: пишем в память, а не на диск ---
    from voice import reminders
    real_add = reminders.ReminderStore.add

    def spy_add(store, kind, fire_at, text=""):
        box.reminders.append({"kind": kind, "fire_at": fire_at, "text": text})
        return real_add(store, kind, fire_at, text)

    reminders.ReminderStore.add = spy_add

    return box


def check_sandboxed():
    """
    Убеждается, что песочница поставлена. Для использования в начале теста.

    Проверяет самое опасное: что браузер подменён.
    """
    from voice import websearch

    if getattr(websearch.webbrowser.open, "__module__", "") != __name__:
        raise RuntimeError(
            "песочница не поставлена: вызовите tools.sandbox.neutralise()")
