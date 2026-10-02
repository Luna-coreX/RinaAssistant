"""
Phrases about other programs' windows (`4.0b-K08`).

«закрой Discord», «сверни телеграм», «разверни хром», «разверни на весь
экран»; on their own «закрой», «сверни», «закрой окно» — the window in
front; and «сверни все окна», «верни окна», «закрой всё».

A pure parse: the router needs an intent, the registry finds the program
and the shell the windows. What is said after the verb is handed on as it
was said — «телеграм», «окно хрома» → «хрома» — and the tool looks it up
the way launching does, so a word taught for «открой» works for «закрой».

**A taken phrase is a whole phrase.** The verb comes first, after nothing
but politeness: «напомни закрыть Discord через час» is a reminder, and the
reminders' stage stands earlier anyway, but «я не могу закрыть окно» is a
complaint, not a command, and is left alone.
"""
from voice.textmatch import normalize

#: The verb -> what is done.
VERBS = {
    "закрой": "close", "закрыть": "close", "закройте": "close",
    "сверни": "minimize", "свернуть": "minimize", "сверните": "minimize",
    "разверни": "expand", "развернуть": "expand", "разверните": "expand",
    "верни": "restore", "вернуть": "restore", "верните": "restore",
    "close": "close", "minimize": "minimize", "minimise": "minimize",
    "maximize": "maximize", "maximise": "maximize",
    # In English «restore Discord» is said, and means what «разверни» does.
    "restore": "expand",
}

#: Words that may come before the verb and change nothing.
POLITE = frozenset({"пожалуйста", "ну", "давай", "можешь", "можно", "а",
                    "please", "can", "you", "could"})

#: Words after the verb that are not the program's name.
FILLER = frozenset({"мне", "пожалуйста", "программу", "приложение", "это",
                    "этот", "эту", "текущее", "текущий", "активное",
                    "активный", "открытое", "please", "the", "this", "app",
                    "current", "active"})

#: «окно» on its own is the one in front; «окна» on its own is all of them.
WINDOW = frozenset({"окно", "window"})
WINDOWS = frozenset({"окна", "окон", "windows"})
ALL = frozenset({"все", "всё", "all", "everything"})

#: «на весь экран» and its kin: expanded to the full screen, not merely
#: back from the taskbar.
FULL = ("на весь экран", "во весь экран", "на полный экран", "full screen",
        "fullscreen")


def classify(text):
    """
    ("close" | "minimize" | "expand" | "maximize", "active" | "all" | app)
    — or None for a phrase that is not about windows.

    «верни» belongs only to «верни (все) окна»: «верни Discord» would be a
    request nobody makes, and «верни как было» is about something else.
    """
    low = normalize(text)
    if not low:
        return None
    for phrase in FULL:
        if phrase in low:
            low = low.replace(phrase, " ").strip()
            full = True
            break
    else:
        full = False

    words = low.split()
    at = next((i for i, w in enumerate(words) if w in VERBS), None)
    if at is None or any(w not in POLITE for w in words[:at]):
        return None
    action = VERBS[words[at]]
    rest = [w for w in words[at + 1:] if w not in FILLER]

    if rest and rest[0] in ALL and set(rest[1:]) <= WINDOWS:
        whole = True
    elif rest and set(rest) <= WINDOWS:
        whole = True
    else:
        whole = False

    if whole:
        if action == "expand":
            action = "restore"
        if action == "maximize":
            return None
        return action, "all"

    if action == "restore":
        return None
    if full and action in ("expand", "maximize"):
        action = "maximize"
    elif full:
        return None

    name = [w for w in rest if w not in WINDOW]
    if not name:
        return action, "active"
    return action, " ".join(name)
