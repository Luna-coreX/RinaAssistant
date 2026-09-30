"""
Управление системой и медиа: громкость, воспроизведение, блокировка, скриншот.

Раньше «системные действия» касались только окна самой Рины (свернуть,
показать, выйти). Здесь — управление компьютером.

Громкость и медиа делаются через эмуляцию мультимедийных клавиш (VK_VOLUME_*,
VK_MEDIA_*): их понимает любой плеер, который слушает эти клавиши, и не нужны
ни внешние библиотеки, ни доступ к конкретному приложению.

Опасные действия (выключение, перезагрузка, сон) помечены confirm=True —
их нельзя выполнять по одной распознанной фразе, ассистент обязан переспросить.
"""

import ctypes
import os
import subprocess
import sys

from core.i18n import t as tr
from core.logging_setup import security_log


# --- виртуальные коды мультимедийных клавиш Windows ---
VK = {
    "volume_mute": 0xAD,
    "volume_down": 0xAE,
    "volume_up": 0xAF,
    "media_next": 0xB0,
    "media_prev": 0xB1,
    "media_stop": 0xB2,
    "media_play_pause": 0xB3,
}

KEYEVENTF_KEYUP = 0x0002
VOLUME_STEP_PRESSES = 4      # одно нажатие меняет громкость примерно на 2%


def _windows():
    return sys.platform.startswith("win")


def system_exe(name, subdir="System32"):
    """
    Абсолютный путь к системной программе.

    По короткому имени Windows ищет программу в том числе в текущей папке,
    поэтому подложенный туда файл выполнился бы вместо системного.
    """
    root = os.environ.get("SystemRoot") or r"C:\Windows"
    full = os.path.join(root, subdir, name)
    return full if os.path.isfile(full) else name


def _tap_key(vk_code, times=1):
    """Эмулирует нажатие клавиши (нажать/отпустить)."""
    if not _windows():
        return False
    try:
        user32 = ctypes.windll.user32
        for _ in range(max(1, times)):
            user32.keybd_event(vk_code, 0, 0, 0)
            user32.keybd_event(vk_code, 0, KEYEVENTF_KEYUP, 0)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Действия
# ---------------------------------------------------------------------------
def volume_up():
    return _tap_key(VK["volume_up"], VOLUME_STEP_PRESSES)


def volume_down():
    return _tap_key(VK["volume_down"], VOLUME_STEP_PRESSES)


def volume_mute():
    return _tap_key(VK["volume_mute"])


def media_play_pause():
    return _tap_key(VK["media_play_pause"])


def media_next():
    return _tap_key(VK["media_next"])


def media_prev():
    return _tap_key(VK["media_prev"])


def lock_workstation():
    if not _windows():
        return False
    try:
        return bool(ctypes.windll.user32.LockWorkStation())
    except Exception:
        return False


def sleep_pc():
    if not _windows():
        return False
    try:
        subprocess.Popen(
            [system_exe("rundll32.exe"), "powrprof.dll,SetSuspendState", "0,1,0"],
            creationflags=0x08000000)
        return True
    except Exception:
        return False


def shutdown_pc():
    if not _windows():
        return False
    try:
        subprocess.Popen([system_exe("shutdown.exe"), "/s", "/t", "0"],
                         creationflags=0x08000000)
        return True
    except Exception:
        return False


def restart_pc():
    if not _windows():
        return False
    try:
        subprocess.Popen([system_exe("shutdown.exe"), "/r", "/t", "0"],
                         creationflags=0x08000000)
        return True
    except Exception:
        return False


def grab_screen():
    """
    Снимок экрана. ВЫЗЫВАТЬ ТОЛЬКО ИЗ ПОТОКА ИНТЕРФЕЙСА: захват экрана —
    операция Qt, из фонового потока она даёт пустую картинку или падает.
    """
    try:
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import QDateTime

        app = QApplication.instance()
        if app is None:
            return None
        screen = app.primaryScreen()
        if screen is None:
            return None
        shot = screen.grabWindow(0)

        pictures = os.path.join(os.path.expanduser("~"), "Pictures")
        if not os.path.isdir(pictures):
            pictures = os.path.expanduser("~")
        stamp = QDateTime.currentDateTime().toString("yyyy-MM-dd_HH-mm-ss")
        path = os.path.join(pictures, f"rina_{stamp}.png")
        return path if shot.save(path, "PNG") else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Разбор команд
# ---------------------------------------------------------------------------
# (фразы, идентификатор, требуется ли подтверждение)
ACTIONS = [
    (("сделай скриншот", "скриншот", "снимок экрана", "screenshot"),
     "screenshot", False),
    (("громче", "прибавь звук", "прибавь громкость", "увеличь громкость",
      "louder", "volume up"), "volume_up", False),
    (("тише", "убавь звук", "убавь громкость", "уменьши громкость",
      "quieter", "volume down"), "volume_down", False),
    (("выключи звук", "включи звук", "без звука", "приглуши", "mute", "unmute"),
     "volume_mute", False),
    (("следующий трек", "следующая песня", "переключи трек", "дальше трек",
      "next track"), "media_next", False),
    (("предыдущий трек", "предыдущая песня", "прошлый трек", "previous track"),
     "media_prev", False),
    (("поставь на паузу", "продолжи воспроизведение", "пауза", "плей",
      "play", "pause"), "media_play_pause", False),
    (("заблокируй компьютер", "заблокируй экран", "блокировка", "lock"),
     "lock", False),
    (("усыпи компьютер", "спящий режим", "в сон", "sleep"), "sleep", True),
    (("перезагрузи компьютер", "перезапусти компьютер", "reboot", "restart"),
     "restart", True),
    (("выключи компьютер", "выключи пк", "заверши работу", "shutdown"),
     "shutdown", True),
]

RUNNERS = {
    "volume_up": volume_up,
    "volume_down": volume_down,
    "volume_mute": volume_mute,
    "media_next": media_next,
    "media_prev": media_prev,
    "media_play_pause": media_play_pause,
    "lock": lock_workstation,
    "sleep": sleep_pc,
    "shutdown": shutdown_pc,
    "restart": restart_pc,
}

DONE_MESSAGES = {
    "volume_up": "Прибавила громкость.",
    "volume_down": "Убавила громкость.",
    "volume_mute": "Переключила звук.",
    "media_next": "Следующий трек.",
    "media_prev": "Предыдущий трек.",
    "media_play_pause": "Готово.",
    "lock": "Блокирую компьютер.",
    "sleep": "Отправляю компьютер в сон.",
    "shutdown": "Выключаю компьютер.",
    "restart": "Перезагружаю компьютер.",
}

CONFIRM_QUESTIONS = {
    "sleep": "Точно отправить компьютер в спящий режим?",
    "shutdown": "Точно выключить компьютер?",
    "restart": "Точно перезагрузить компьютер?",
}


def match_action(text):
    """
    Возвращает (action_id, needs_confirm) или (None, False).

    Два прохода, и порядок между ними важнее длины фразы.

    Сначала точное вхождение, от длинных фраз к коротким: «выключи звук» не
    должно срабатывать как «выключи компьютер».

    И только потом — неточное, для оговорок и ошибок распознавания. Раньше
    проход был один, и «убавь громкость» делало ГРОМЧЕ: неточное сравнение
    считает её похожей на «прибавь громкость» (0.875 при пороге 0.82), а та
    длиннее и потому проверялась первой. Точное совпадение обязано побеждать
    приблизительное, какой бы длины оно ни было.
    """
    from voice.textmatch import normalize, contains_phrase

    low = normalize(text)
    if not low:
        return None, False

    ranked = []
    for phrases, action_id, confirm in ACTIONS:
        for phrase in phrases:
            ranked.append((len(phrase), phrase, action_id, confirm))
    ranked.sort(reverse=True)

    for _length, phrase, action_id, confirm in ranked:
        if normalize(phrase) in low:
            return action_id, confirm

    for _length, phrase, action_id, confirm in ranked:
        if contains_phrase(low, phrase):
            return action_id, confirm
    return None, False


#: Действия, которые выполняет оболочка, а не ядро.
#: Снимок экрана — операция интерфейса: из фонового потока она даёт пустую
#: картинку или падает. Ядро только сообщает о намерении.
WINDOW_ACTIONS = frozenset({"screenshot"})


def run(action_id):
    """
    Выполняет действие, возвращает текст ответа.

    Действия из WINDOW_ACTIONS здесь НЕ выполняются: их делает оболочка,
    а сообщить ей об этом — дело исполнителя, у которого есть своя шина.
    Раньше отсюда шло событие в модульный синглтон `core.events.bus`, и
    из-за этого ядро нельзя было поднять дважды: событие уходило мимо
    обоих (см. 4.0-B05).
    """
    if action_id in WINDOW_ACTIONS:
        return tr("Делаю скриншот.")

    runner = RUNNERS.get(action_id)
    if runner is None:
        return None
    if action_id in CONFIRM_QUESTIONS:
        # питание и сон — ровно то, ради чего существует подтверждение
        security_log().warning("Выполняется системное действие: %s", action_id)
    if runner():
        return tr(DONE_MESSAGES.get(action_id, "Готово."))
    return tr("Не получилось выполнить действие.")


def confirm_question(action_id):
    return tr(CONFIRM_QUESTIONS.get(action_id, "Точно выполнить?"))
