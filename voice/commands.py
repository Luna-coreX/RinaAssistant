"""
The assistant's built-in commands (what the plugins do not cover).

Launching programs hardly comes here: voice/app_launcher deals with that
using the index of installed software. The catalogue below remains a
fallback path for systems where the index is empty.

Launching on Windows goes by an absolute path and without a shell. There
used to be `Popen("discord", shell=True)` here: Windows's search order
includes the current working directory, so a `discord.exe` file placed next
to the application would run instead of the real program.
"""

import os
import shutil
import subprocess
import sys

from core.i18n import t as tr
from core.logging_setup import get_logger


log = get_logger("commands")


# The catalogue of known applications: a keyword -> commands for each OS.
APPS = {
    "discord": {
        "names": ["discord", "дискорд"],
        "win": "discord.exe",
        "darwin": "Discord",
        "linux": "discord",
        "label": "Discord",
    },
    "browser": {
        "names": ["браузер", "browser", "хром", "chrome"],
        "win": "chrome.exe",
        "default_browser": True,
        "darwin": "Google Chrome",
        "linux": "google-chrome",
        "label": "браузер",
    },
    "notepad": {
        "names": ["блокнот", "notepad", "заметки"],
        "win": "notepad.exe",
        "darwin": "TextEdit",
        "linux": "gedit",
        "label": "блокнот",
    },
    "calculator": {
        "names": ["калькулятор", "calculator", "calc"],
        "win": "calc.exe",
        "darwin": "Calculator",
        "linux": "gnome-calculator",
        "label": "калькулятор",
    },
    "explorer": {
        "names": ["проводник", "файлы", "explorer", "finder"],
        "win": "explorer.exe",
        "darwin": "Finder",
        "linux": "xdg-open .",
        "label": "проводник",
    },
}


def _windows_exe(name):
    """
    The absolute path to an executable, or None.

    We look ourselves rather than relying on Windows's search: its order
    includes the current working directory, and a file slipped in there
    would run instead of the real one. We check the system directories
    first, and PATH last.
    """
    root = os.environ.get("SystemRoot") or r"C:\Windows"
    for folder in (os.path.join(root, "System32"), root):
        candidate = os.path.join(folder, name)
        if os.path.isfile(candidate):
            return candidate
    return shutil.which(name)


def _launch_windows(app) -> bool:
    path = _windows_exe(app["win"])
    if path:
        subprocess.Popen([path])
        return True
    if app.get("default_browser"):
        # a particular Chrome may not be there, while a default browser
        # always is — opening that is more honest than answering with a refusal
        import webbrowser
        return bool(webbrowser.open("about:blank"))
    return False


def _launch(app_key) -> bool:
    """Tries to launch an application. True on success."""
    app = APPS[app_key]
    platform = sys.platform
    try:
        if platform.startswith("win"):
            return _launch_windows(app)
        if platform == "darwin":
            subprocess.Popen(["open", "-a", app["darwin"]])
            return True
        # linux and the rest
        cmd = app["linux"]
        exe = cmd.split()[0]
        if shutil.which(exe) is None and exe != "xdg-open":
            return False
        subprocess.Popen(cmd.split())
        return True
    except Exception:
        log.exception("Не удалось запустить %s", app.get("label", app_key))
        return False


def handle_builtin_command(text):
    """
    Parses the text and performs a built-in command.
    Returns an answer string (to speak/toast), or None if nothing was
    recognised.
    """
    from voice.textmatch import normalize, contains_phrase
    from voice import calculator, websearch
    from core.settings_store import settings

    low = normalize(text)

    # --- arithmetic: "посчитай 15*12", "20% от 3000" ---
    calculated = calculator.try_calculate(text)
    if calculated:
        return calculated

    # --- an explicit web search: "найди рецепт борща" ---
    found = websearch.try_search(
        text, settings.get("search_engine", websearch.DEFAULT_ENGINE))
    if found:
        return found

    # Launching programs no longer comes here: voice/app_launcher deals with
    # it using the index of installed software (it is called earlier in the
    # command pipeline). APPS/_launch stayed as a fallback catalogue for
    # systems without an index.

    # --- simple built-in answers ---
    topic = match_answer(low)
    if topic:
        return ANSWERS[topic]()

    return None


# A topic -> how to answer. As a separate table, so that the router
# (4.0-B02) can determine the topic without receiving a ready-made phrase:
# an intent and its speaking are different things, and after the split the
# text of an answer is assembled by the core, not by the parse.
ANSWERS = {
    "name": lambda: tr("Меня зовут Рина, я твой голосовой ассистент."),
    "thanks": lambda: tr("Всегда пожалуйста!"),
    "capabilities": lambda: tr(
        "Я могу запускать приложения, считать, искать в интернете и "
        "выполнять команды плагинов. Попробуй сказать: запусти браузер."),
}

ANSWER_PHRASES = {
    "name": ("как тебя зовут", "твоё имя", "твое имя", "your name",
             "who are you"),
    "thanks": ("спасибо", "благодарю", "thank", "thanks"),
    "capabilities": ("что ты умеешь", "твои возможности", "what can you do",
                     "your capabilities"),
}


def match_answer(low):
    """The topic of a built-in answer, or None. A pure function."""
    for topic, phrases in ANSWER_PHRASES.items():
        if any(phrase in low for phrase in phrases):
            return topic
    return None


def known_commands():
    """For showing in the UI (the "Commands" tab)."""
    cmds = [
        (tr("Запусти <название программы>"),
         tr("Находит и запускает любую установленную программу")),
        (tr("Запусти браузер"), tr("Открывает установленный браузер")),
    ]
    cmds += [
        (tr("Громче / тише"), tr("Меняет громкость системы")),
        (tr("Пауза / следующий трек"), tr("Управляет воспроизведением")),
        (tr("Сделай скриншот"), tr("Сохраняет снимок экрана в «Изображения»")),
        (tr("Заблокируй компьютер"), tr("Блокирует рабочий стол")),
        (tr("Выключи компьютер"), tr("Выключение — с подтверждением")),
    ]
    cmds.append((tr("Посчитай 15 * 12"), tr("Считает выражение, проценты и доли")))
    cmds.append((tr("Найди рецепт борща"), tr("Ищет запрос в интернете")))
    cmds.append((tr("Как тебя зовут"), tr("Ассистент представляется")))
    cmds.append((tr("Что ты умеешь"), tr("Список возможностей")))
    return cmds
