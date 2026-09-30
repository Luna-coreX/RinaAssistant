"""
A die and a coin.

An example of a tool **with an argument**: a die can have different numbers
of faces. Arguments are described with the same `Param` as the core's
built-in tools, and are checked by the registry — a plugin has neither to
parse nor to trust.
"""
import random

from core.tools import Param
from plugins.api import Plugin, PluginTool


class DicePlugin(Plugin):
    """A die and a coin."""

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
