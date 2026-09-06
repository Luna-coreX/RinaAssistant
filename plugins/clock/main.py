"""
The clock: the time and the date.

An example of a **declared tool** (API v4). The plugin does not answer
itself — it declares that it can say the time, and the core calls that when
it decides the person asked about the time. It asks for no permissions: the
clock is read from the system, and the system time is no secret.
"""
from datetime import datetime

from plugins.api import Plugin, PluginTool


class ClockPlugin(Plugin):
    """The time/date plugin."""

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

    # Phrase parsing stays: a language model will call the tools when it
    # comes to that, and until then the plugin parses the phrase itself.
    def on_command(self, text):
        low = text.lower()
        if "время" in low or "который час" in low or "сколько времени" in low:
            self.respond(f"Сейчас {datetime.now():%H:%M}.")
            return True
        if "дата" in low or "какое число" in low or "какой день" in low:
            self.respond(f"Сегодня {datetime.now():%d.%m.%Y}.")
            return True
        return False
