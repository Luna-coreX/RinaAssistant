"""
The contract between the core and the shell.

Listed here is every event the core publishes, and what their data consists
of. This is the only place where their format is described: when the shell
moves to another process (or to another language), the contract becomes an
IPC protocol rather than a set of understandings scattered through the code.

The rule: an event's data is simple values (strings, numbers, dicts, lists)
fit for serialisation into JSON. There are no exceptions: everything that
cannot be written to JSON (the programs found during a clarifying question,
for instance) stays inside the core and does not go out.
"""

PROTOCOL_VERSION = 1


class Events:
    # --- the microphone ---
    LISTENING_STARTED = "listening.started"   # {}
    LISTENING_STOPPED = "listening.stopped"   # {}
    CAPTURING = "listening.capturing"         # {"active": bool}
    ALWAYS_LISTEN = "listening.always"        # {"enabled": bool}
    RECOGNIZED = "speech.recognized"          # {"text": str}

    # --- the assistant's answers ---
    RESPONSE = "assistant.response"           # {"text": str}
    ERROR = "assistant.error"                 # {"text": str}
    # the model is thinking about an answer: this may take seconds, and the
    # shell had better show an indicator rather than stay silent
    THINKING = "assistant.thinking"           # {"active": bool}

    # --- data ---
    HISTORY_CHANGED = "history.changed"       # {}
    REMINDER_FIRED = "reminder.fired"         # {"item": dict}

    # --- requests to the shell ---
    # The core cannot show windows: it reports an intent, and the shell
    # decides how that looks (and whether to show it at all).
    APP_NOT_FOUND = "apps.not_found"          # {"query": str}
    WINDOW_ACTION = "window.action"           # {"action": str}


#: Every known event — handy for checks and for debugging.
ALL_EVENTS = tuple(
    value for name, value in vars(Events).items()
    if not name.startswith("_") and isinstance(value, str)
)
