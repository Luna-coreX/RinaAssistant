import random
from plugins.api import Plugin


class DicePlugin(Plugin):
    """Кубик и монетка."""

    def on_command(self, text):
        low = text.lower()
        if "кубик" in low or "кость" in low:
            self.respond(f"🎲 Выпало: {random.randint(1, 6)}")
            return True
        if "монет" in low:
            self.respond("🪙 " + random.choice(["Орёл!", "Решка!"]))
            return True
        return False
