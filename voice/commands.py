"""
Встроенные команды ассистента (то, что не покрыто плагинами).

Запуск программ сюда почти не попадает: этим занимается voice/app_launcher
по индексу установленного ПО. Каталог ниже остался запасным путём для
систем, где индекс пуст.

Запуск на Windows идёт по абсолютному пути и без оболочки. Раньше здесь
было `Popen("discord", shell=True)`: порядок поиска Windows включает текущую
рабочую папку, поэтому файл `discord.exe`, положенный рядом с приложением,
выполнился бы вместо настоящей программы.
"""

import os
import shutil
import subprocess
import sys

from core.i18n import t as tr
from core.logging_setup import get_logger


log = get_logger("commands")


# Каталог известных приложений: ключевое слово -> команды под каждую ОС.
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
    Абсолютный путь к исполняемому файлу или None.

    Ищем сами, а не полагаемся на поиск Windows: его порядок включает
    текущую рабочую папку, и подложенный туда файл выполнился бы вместо
    настоящего. Системные каталоги проверяем первыми, PATH — последним.
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
        # конкретного Chrome может не быть, а браузер по умолчанию есть
        # всегда — открыть его честнее, чем ответить отказом
        import webbrowser
        return bool(webbrowser.open("about:blank"))
    return False


def _launch(app_key) -> bool:
    """Пытается запустить приложение. True при успехе."""
    app = APPS[app_key]
    platform = sys.platform
    try:
        if platform.startswith("win"):
            return _launch_windows(app)
        if platform == "darwin":
            subprocess.Popen(["open", "-a", app["darwin"]])
            return True
        # linux и прочее
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
    Разбирает текст и выполняет встроенную команду.
    Возвращает строку-ответ (для озвучки/toast) или None, если не распознано.
    """
    from voice.textmatch import normalize, contains_phrase
    from voice import calculator, websearch
    from core.settings_store import settings

    low = normalize(text)

    # --- арифметика: «посчитай 15*12», «20% от 3000» ---
    calculated = calculator.try_calculate(text)
    if calculated:
        return calculated

    # --- явный веб-поиск: «найди рецепт борща» ---
    found = websearch.try_search(
        text, settings.get("search_engine", websearch.DEFAULT_ENGINE))
    if found:
        return found

    # Запуск программ сюда больше не попадает: им занимается voice/app_launcher
    # по индексу установленного ПО (он вызывается раньше в конвейере команд).
    # APPS/_launch остались как запасной каталог для систем без индекса.

    # --- простые встроенные ответы ---
    topic = match_answer(low)
    if topic:
        return ANSWERS[topic]()

    return None


# Тема -> как ответить. Отдельной таблицей, чтобы роутер (4.0-B02) мог
# определить тему, не получая готовую фразу: намерение и его озвучка — разные
# вещи, и после разделения текст ответа собирает ядро, а не разбор.
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
    """Тема встроенного ответа или None. Чистая функция."""
    for topic, phrases in ANSWER_PHRASES.items():
        if any(phrase in low for phrase in phrases):
            return topic
    return None


def known_commands():
    """Для отображения в UI (вкладка «Команды»)."""
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
