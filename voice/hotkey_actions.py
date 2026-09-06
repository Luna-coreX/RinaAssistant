"""
Actions that can be assigned hotkeys.

The main "listen" action is already governed by settings["hotkey"]. Here are
the extra actions the user can bind on the "Hotkeys" tab. Their combinations
are kept in settings["action_hotkeys"].
"""

# id -> (label, description, icon)
HOTKEY_ACTIONS = {
    "listen":        ("Слушать (микрофон)", "Начать разовое распознавание", "🎤"),
    "toggle_always": ("Режим «всегда слушать»", "Вкл/выкл постоянное прослушивание", "👂"),
    "show_hide":     ("Показать/скрыть окно", "Свернуть в трей или развернуть", "🪟"),
    "mute":          ("Вкл/выкл озвучку", "Переключить голосовые ответы", "🔇"),
    "focus_command": ("Фокус на строку команд", "Перейти к вводу команды", "⌨️"),
    "floating_bar":  ("Плавающая строка команд", "Показать/скрыть строку поверх окон", "💬"),
}


def action_meta(action_id):
    return HOTKEY_ACTIONS.get(action_id, (action_id, "", "•"))
