"""
Контракт между ядром и оболочкой.

Здесь перечислены все события, которые публикует ядро, и состав их данных.
Это единственное место, где описан их формат: когда оболочка переедет в
другой процесс (или на другой язык), контракт станет протоколом IPC, а не
набором договорённостей, разбросанных по коду.

Правило: данные события — простые значения (строки, числа, словари, списки),
пригодные к сериализации в JSON. Исключений нет: всё, что нельзя записать в
JSON (например, найденные программы при уточняющем вопросе), остаётся внутри
ядра и наружу не выходит.
"""

PROTOCOL_VERSION = 1


class Events:
    # --- микрофон ---
    LISTENING_STARTED = "listening.started"   # {}
    LISTENING_STOPPED = "listening.stopped"   # {}
    CAPTURING = "listening.capturing"         # {"active": bool}
    ALWAYS_LISTEN = "listening.always"        # {"enabled": bool}
    RECOGNIZED = "speech.recognized"          # {"text": str}

    # --- ответы ассистента ---
    RESPONSE = "assistant.response"           # {"text": str}
    ERROR = "assistant.error"                 # {"text": str}
    # модель думает над ответом: это может занять секунды, и оболочке стоит
    # показать индикатор, а не молчать
    THINKING = "assistant.thinking"           # {"active": bool}

    # --- данные ---
    HISTORY_CHANGED = "history.changed"       # {}
    REMINDER_FIRED = "reminder.fired"         # {"item": dict}

    # --- запросы к оболочке ---
    # Ядро не умеет показывать окна: оно сообщает о намерении, а оболочка
    # решает, как это выглядит (и показывать ли вообще).
    APP_NOT_FOUND = "apps.not_found"          # {"query": str}
    WINDOW_ACTION = "window.action"           # {"action": str}


#: Все известные события — удобно для проверок и отладки.
ALL_EVENTS = tuple(
    value for name, value in vars(Events).items()
    if not name.startswith("_") and isinstance(value, str)
)
