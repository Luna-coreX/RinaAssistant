"""
A greeting.

An example of the **smallest** plugin: no tools, no page, no permissions —
only phrase parsing. And so it should be: declaring a tool for the sake of
"hello" is pointless, and the API requires declaring nothing.
"""
from plugins.api import Plugin


class GreeterPlugin(Plugin):
    """A simple greeting plugin — a demonstration of on_command."""

    def on_enable(self):
        self.log("Плагин приветствия готов")

    def on_command(self, text):
        low = text.lower()
        if any(w in low for w in ("привет", "здравствуй", "хай", "hello")):
            name = self.ctx.get_setting("user_name", "друг")
            self.respond(f"Привет, {name}! Чем могу помочь?")
            return True
        if "пока" in low or "до свидания" in low:
            self.respond("До встречи! 🌸")
            return True
        return False
