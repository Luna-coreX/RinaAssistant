"""
Приветствие.

Пример **самого маленького** плагина: ни инструментов, ни страницы, ни
разрешений — только разбор фразы. Так и должно быть: объявлять инструмент
ради «привет» незачем, и API не требует объявлять ничего.
"""
from plugins.api import Plugin


class GreeterPlugin(Plugin):
    """Простой плагин-приветствие — демонстрация on_command."""

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
