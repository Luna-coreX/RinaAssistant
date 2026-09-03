"""
Кубик и монетка.

Пример инструмента **с аргументом**: у кубика бывает разное число граней.
Аргументы описываются теми же `Param`, что у встроенных инструментов ядра,
и проверяются реестром — плагину не приходится ни разбирать, ни доверять.
"""
import random

from core.tools import Param
from plugins.api import Plugin, PluginTool


class DicePlugin(Plugin):
    """Кубик и монетка."""

    def tools(self):
        return [
            PluginTool(
                name="roll",
                summary="Бросить кубик.",
                params=(Param("sides", "integer",
                              "Сколько граней; по умолчанию шесть.",
                              required=False, minimum=2, maximum=100),),
                run=self._roll,
            ),
            PluginTool(
                name="flip",
                summary="Подбросить монетку.",
                run=lambda args: random.choice(["Орёл!", "Решка!"]),
            ),
        ]

    @staticmethod
    def _roll(args):
        sides = int(args.get("sides") or 6)
        return f"🎲 Выпало: {random.randint(1, sides)}"

    def on_command(self, text):
        low = text.lower()
        if "кубик" in low or "кость" in low:
            self.respond(f"🎲 Выпало: {random.randint(1, 6)}")
            return True
        if "монет" in low:
            self.respond("🪙 " + random.choice(["Орёл!", "Решка!"]))
            return True
        return False
