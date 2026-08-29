"""
Пользовательские команды.

Пользователь создаёт команды через конструктор на вкладке «Команды».
Каждая команда — словарь:

    {
        "id": "cmd_ab12",
        "enabled": True,
        "type": "app" | "folder" | "website" | "speak" | "system" | "sequence",
        "triggers": ["запусти дискорд", "открой discord"],  # фразы активации
        "match": "contains" | "exact",                       # режим совпадения
        "target": "...",   # путь / url / текст / имя действия (зависит от типа)
        "response": "Хорошо, запускаю Discord",              # что ответить (опц.)
        "steps": [ {подкоманды} ],                           # только для sequence
    }

Хранятся в общем конфиге (settings["custom_commands"]).
Выполнение кроссплатформенное: приложения/папки/сайты открываются штатными
средствами ОС.
"""

import os
import sys
import uuid
import shutil
import subprocess
import webbrowser


COMMAND_TYPES = [
    ("app",      "Программа",        "🖥️"),
    ("folder",   "Папка",            "📁"),
    ("website",  "Сайт",             "🌐"),
    ("speak",    "Озвучить текст",   "🔊"),
    ("system",   "Системное действие", "⚙️"),
    ("sequence", "Последовательность", "🔗"),
]

# Действия над окном самой Рины выполняет главное окно (host),
# действия с префиксом sys_ — voice/system_control (громкость, медиа, ПК).
SYSTEM_ACTIONS = [
    ("minimize",             "Свернуть окно Рины"),
    ("show",                 "Показать окно Рины"),
    ("quit",                 "Выйти из Рины"),
    ("mute",                 "Отключить озвучку"),
    ("unmute",               "Включить озвучку"),
    ("sys_volume_up",        "Прибавить громкость"),
    ("sys_volume_down",      "Убавить громкость"),
    ("sys_volume_mute",      "Переключить звук системы"),
    ("sys_media_play_pause", "Пауза / продолжить"),
    ("sys_media_next",       "Следующий трек"),
    ("sys_media_prev",       "Предыдущий трек"),
    ("sys_screenshot",       "Сделать скриншот"),
    ("sys_lock",             "Заблокировать компьютер"),
    ("sys_sleep",            "Спящий режим"),
    ("sys_restart",          "Перезагрузить компьютер"),
    ("sys_shutdown",         "Выключить компьютер"),
]

# Действия, которые нельзя выполнять без подтверждения: ошибка распознавания
# или случайно совпавшая фраза не должна выключать компьютер.
DESTRUCTIVE_ACTIONS = {"sys_shutdown", "sys_restart", "sys_sleep", "quit"}


def action_label(action_id):
    for aid, label in SYSTEM_ACTIONS:
        if aid == action_id:
            return label
    return action_id


def command_needs_confirm(command):
    """Есть ли в команде (или её шагах) необратимое действие."""
    if command.get("type") == "system":
        return command.get("target") in DESTRUCTIVE_ACTIONS
    if command.get("type") == "sequence":
        return any(step.get("type") == "system"
                   and step.get("target") in DESTRUCTIVE_ACTIONS
                   for step in command.get("steps", []))
    return False


def new_command_id():
    return "cmd_" + uuid.uuid4().hex[:6]


def make_command(cmd_type="app", triggers=None, target="", response="",
                 match="contains", enabled=True, steps=None,
                 target_kind="file"):
    return {
        "id": new_command_id(),
        "enabled": bool(enabled),
        "type": cmd_type,
        "triggers": triggers or [],
        "match": match,
        "target": target,
        # чем является target: файл/путь или идентификатор приложения Магазина
        "target_kind": target_kind,
        "response": response,
        "steps": steps or [],
    }


def type_label(cmd_type):
    for t, label, _ in COMMAND_TYPES:
        if t == cmd_type:
            return label
    return cmd_type


def type_icon(cmd_type):
    for t, _, icon in COMMAND_TYPES:
        if t == cmd_type:
            return icon
    return "•"


# ---------------------------------------------------------------------------
# Хранилище
# ---------------------------------------------------------------------------
class UserCommandStore:
    def __init__(self, settings):
        self._settings = settings

    def all(self):
        return list(self._settings.get("custom_commands", []) or [])

    def save_all(self, commands):
        self._settings.set("custom_commands", commands)
        self._settings.save()

    def add(self, command):
        cmds = self.all()
        cmds.append(command)
        self.save_all(cmds)

    def update(self, command):
        cmds = self.all()
        for i, c in enumerate(cmds):
            if c.get("id") == command.get("id"):
                cmds[i] = command
                break
        self.save_all(cmds)

    def remove(self, command_id):
        cmds = [c for c in self.all() if c.get("id") != command_id]
        self.save_all(cmds)

    def set_enabled(self, command_id, enabled):
        cmds = self.all()
        for c in cmds:
            if c.get("id") == command_id:
                c["enabled"] = bool(enabled)
        self.save_all(cmds)

    # статистика запусков
    def bump_stat(self, command_id):
        stats = dict(self._settings.get("command_stats", {}) or {})
        stats[command_id] = stats.get(command_id, 0) + 1
        self._settings.set("command_stats", stats)
        self._settings.save()

    def stat(self, command_id):
        return (self._settings.get("command_stats", {}) or {}).get(command_id, 0)


# ---------------------------------------------------------------------------
# Сопоставление и выполнение
# ---------------------------------------------------------------------------
def matches(command, text):
    """
    Подходит ли команда под распознанный текст.

    Сравнение нечёткое: распознавание речи путает окончания и буквы
    («зопусти дискорт»), а точное вхождение подстроки такие варианты теряет.
    Режим «Точное совпадение» тоже допускает погрешность распознавания,
    но требует совпадения фразы целиком, а не её вхождения.
    """
    if not command.get("enabled", True):
        return False

    from voice.textmatch import similar, contains_phrase

    exact_mode = command.get("match") == "exact"
    for trig in command.get("triggers", []):
        trigger = str(trig).strip()
        if not trigger:
            continue
        if exact_mode:
            if similar(text, trigger):
                return True
        else:
            if contains_phrase(text, trigger):
                return True
    return False


def _open_path(path):
    """Открыть файл/папку/приложение штатно для ОС."""
    if not path:
        return False
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)  # noqa
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            # если это исполняемый в PATH — запустим, иначе xdg-open
            if shutil.which(path):
                subprocess.Popen([path])
            else:
                subprocess.Popen(["xdg-open", path])
        return True
    except Exception:
        return False


def execute(command, host=None):
    """
    Выполняет команду. host — объект с методами для системных действий
    (minimize/show/quit/mute/unmute) и say(text). Возвращает (ok, response_text).
    """
    ctype = command.get("type")
    target = command.get("target", "")
    response = command.get("response", "")

    ok = True
    if ctype == "app" and command.get("target_kind") == "uwp":
        # приложение Магазина: запускается по идентификатору, а не по пути
        from voice import app_index
        ok = app_index.launch(
            app_index.AppEntry(target, target, "uwp", "learned"))
    elif ctype == "app" or ctype == "folder":
        ok = _open_path(target)
    elif ctype == "website":
        url = target
        if url and not url.startswith(("http://", "https://")):
            url = "https://" + url
        try:
            webbrowser.open(url)
        except Exception:
            ok = False
    elif ctype == "speak":
        # для «озвучить текст» ответом является сам текст (target),
        # если отдельный response не задан
        if not response:
            response = target
    elif ctype == "system":
        ok = _run_system_action(target, host)
    elif ctype == "pause":
        # пауза между шагами: дать программе время запуститься.
        # Ограничиваем сверху, чтобы опечатка не подвесила выполнение надолго.
        import time
        try:
            seconds = max(0.0, min(float(str(target).replace(",", ".")), 60.0))
        except (TypeError, ValueError):
            seconds = 1.0
        time.sleep(seconds)
        ok = True
    elif ctype == "sequence":
        ok = True
        for step in command.get("steps", []):
            step_ok, _ = execute(step, host)
            ok = ok and step_ok
    else:
        ok = False

    if not response:
        # дефолтный ответ
        response = _default_response(command, ok)
    return ok, response


def _run_system_action(action, host):
    # действия с компьютером (громкость, медиа, блокировка) — им host не нужен
    if str(action).startswith("sys_"):
        from voice import system_control
        from core.i18n import t as tr
        message = system_control.run(action[4:])
        # run() возвращает текст и при неудаче — сравниваем именно с ним,
        # иначе шаг последовательности отчитывался бы «Готово» после сбоя
        return bool(message) and message != tr("Не получилось выполнить действие.")

    # действия над окном Рины трогают виджеты, а команда может выполняться
    # в фоновом потоке (распознавание речи) — уводим их в GUI-поток сигналом
    mapping = {
        "minimize": "action_minimize",
        "show": "action_show",
        "quit": "action_quit",
        "mute": "action_mute",
        "unmute": "action_unmute",
    }
    if action not in mapping:
        return False
    try:
        from core.events import bus
        from core.protocol import Events
        bus.emit(Events.WINDOW_ACTION, action=action)
        return True
    except Exception:
        pass
    # запасной путь, если сигнальная шина недоступна
    if host is not None and hasattr(host, mapping[action]):
        try:
            getattr(host, mapping[action])()
            return True
        except Exception:
            return False
    return False


def _default_response(command, ok):
    from core.i18n import t as tr

    ctype = command.get("type")
    if not ok:
        return tr("Не получилось выполнить команду.")
    if ctype == "app":
        return tr("Запускаю программу.")
    if ctype == "folder":
        return tr("Открываю папку.")
    if ctype == "website":
        return tr("Открываю сайт.")
    if ctype == "speak":
        return command.get("target", "")
    if ctype == "system":
        return tr("Готово.")
    if ctype == "sequence":
        return tr("Выполняю последовательность.")
    return tr("Готово.")
