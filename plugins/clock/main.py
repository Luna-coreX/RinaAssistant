"""
Часы: время и дата.

Пример **объявленного инструмента** (API v4). Плагин не отвечает сам —
он объявляет, что умеет сказать время, и ядро зовёт это, когда решит, что
человек спросил именно про время. Разрешений не просит: часы читаются из
системы, а системное время не тайна.
"""
from datetime import datetime

from plugins.api import Plugin, PluginTool


class ClockPlugin(Plugin):
    """Плагин времени/даты."""

    def tools(self):
        return [
            PluginTool(
                name="time",
                summary="Сказать текущее время.",
                run=lambda args: f"Сейчас {datetime.now():%H:%M}.",
            ),
            PluginTool(
                name="date",
                summary="Сказать сегодняшнюю дату.",
                run=lambda args: f"Сегодня {datetime.now():%d.%m.%Y}.",
            ),
        ]

    # Разбор фразы остаётся: инструменты позовёт языковая модель, когда
    # дойдёт до этого дело, а до тех пор фразу разбирает плагин сам.
    def on_command(self, text):
        low = text.lower()
        if "время" in low or "который час" in low or "сколько времени" in low:
            self.respond(f"Сейчас {datetime.now():%H:%M}.")
            return True
        if "дата" in low or "какое число" in low or "какой день" in low:
            self.respond(f"Сегодня {datetime.now():%d.%m.%Y}.")
            return True
        return False
