from datetime import datetime
from plugins.api import Plugin


class ClockPlugin(Plugin):
    """Плагин времени/даты."""

    def on_command(self, text):
        low = text.lower()
        if "время" in low or "который час" in low or "сколько времени" in low:
            now = datetime.now().strftime("%H:%M")
            self.respond(f"Сейчас {now}.")
            return True
        if "дата" in low or "какое число" in low or "какой день" in low:
            today = datetime.now().strftime("%d.%m.%Y")
            self.respond(f"Сегодня {today}.")
            return True
        return False
