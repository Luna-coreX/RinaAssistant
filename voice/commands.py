"""
Встроенные команды ассистента (то, что не покрыто плагинами).

Основной кейс — запуск приложений: «Рина, запусти Discord».
Кроссплатформенный запуск: на Windows через `start`, на macOS через `open`,
на Linux через сам исполняемый файл. Возвращаем текст ответа, который
ассистент озвучит и покажет в toast.
"""

from core.i18n import t as tr
import sys
import shutil
import subprocess


# Каталог известных приложений: ключевое слово -> команды под каждую ОС.
APPS = {
    "discord": {
        "names": ["discord", "дискорд"],
        "win": "discord",
        "darwin": "Discord",
        "linux": "discord",
        "label": "Discord",
    },
    "browser": {
        "names": ["браузер", "browser", "хром", "chrome"],
        "win": "start chrome",
        "darwin": "Google Chrome",
        "linux": "google-chrome",
        "label": "браузер",
    },
    "notepad": {
        "names": ["блокнот", "notepad", "заметки"],
        "win": "notepad",
        "darwin": "TextEdit",
        "linux": "gedit",
        "label": "блокнот",
    },
    "calculator": {
        "names": ["калькулятор", "calculator", "calc"],
        "win": "calc",
        "darwin": "Calculator",
        "linux": "gnome-calculator",
        "label": "калькулятор",
    },
    "explorer": {
        "names": ["проводник", "файлы", "explorer", "finder"],
        "win": "explorer",
        "darwin": "Finder",
        "linux": "xdg-open .",
        "label": "проводник",
    },
}


def _launch(app_key) -> bool:
    """Пытается запустить приложение. True при успехе."""
    app = APPS[app_key]
    platform = sys.platform
    try:
        if platform.startswith("win"):
            subprocess.Popen(app["win"], shell=True)
        elif platform == "darwin":
            subprocess.Popen(["open", "-a", app["darwin"]])
        else:  # linux и прочее
            cmd = app["linux"]
            exe = cmd.split()[0]
            if shutil.which(exe) is None and exe != "xdg-open":
                return False
            subprocess.Popen(cmd.split())
        return True
    except Exception:
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
    if ("как тебя зовут" in low or "твоё имя" in low or "твое имя" in low
            or "your name" in low or "who are you" in low):
        return tr("Меня зовут Рина, я твой голосовой ассистент.")

    if ("спасибо" in low or "благодарю" in low
            or "thank" in low or "thanks" in low):
        return tr("Всегда пожалуйста!")

    if ("что ты умеешь" in low or "твои возможности" in low
            or "what can you do" in low or "your capabilities" in low):
        return tr("Я могу запускать приложения, считать, искать в интернете и "
                  "выполнять команды плагинов. Попробуй сказать: запусти браузер.")

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
