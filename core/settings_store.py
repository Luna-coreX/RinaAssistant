"""
Хранилище настроек приложения — разделённое на несколько файлов.

Данные физически лежат в нескольких JSON в пользовательской папке:
  Windows: %APPDATA%/RinaAssistant/
  Linux:   ~/.config/RinaAssistant/
  macOS:   ~/Library/Application Support/RinaAssistant/

Файлы:
  settings.json  — настройки приложения и страницы «Рина»
  commands.json  — пользовательские команды и статистика запусков
  plugins.json   — включённые плагины и их настройки
  history.json   — журнал взаимодействий

Снаружи это по-прежнему ОДИН объект `settings` с get/set/save — код,
который читает settings.get("history") и т.п., менять не нужно. Роутинг ключа
в нужный файл происходит внутри. При первом запуске после обновления старый
монолитный settings.json автоматически мигрирует в новые файлы.
"""

import os
import sys
import json
import tempfile


APP_NAME = "RinaAssistant"


# Значения по умолчанию, сгруппированные по файлам.
GROUPS = {
    "settings": {
        # --- страница «Рина» ---
        "voice": "default",
        "wake_word": "Рина",
        "wake_words": ["Рина", "Rina"],
        "volume": 75,
        "speed": 100,
        "language": "Русский",
        "voice_reply": True,
        "always_listen": False,
        "tts_engine": "silent",
        "stt_engine": "disabled",
        "input_device": "default",
        "output_device": "default",
        "vosk_model": "",
        "whisper_model": "base",
        "piper_model": "",
        # --- приложение ---
        "theme": "Catppuccin Mocha",
        "accent": "Mauve",
        "ui_language": "Русский",
        "autostart": False,
        "minimize_to_tray": True,
        "start_minimized": False,
        "floating_command_bar": False,
        "notifications": True,
        "sound_effects": True,
        "check_updates": True,
        "hotkey": "Ctrl+Shift+R",
        "action_hotkeys": {},
        "save_history": True,
        "telemetry": False,
        "first_run": True,
    },
    "commands": {
        "custom_commands": [],
        "command_stats": {},
    },
    "plugins": {
        "enabled_plugins": [],
        "plugin_settings": {},
    },
    "history": {
        "history": [],
    },
}

# Плоский словарь всех дефолтов (для обратной совместимости API).
DEFAULTS = {}
for _grp in GROUPS.values():
    DEFAULTS.update(_grp)

# Обратный индекс: ключ -> имя файла/группы.
_KEY_TO_GROUP = {}
for _name, _grp in GROUPS.items():
    for _k in _grp:
        _KEY_TO_GROUP[_k] = _name


def _config_dir() -> str:
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.environ.get(
            "XDG_CONFIG_HOME", os.path.expanduser("~/.config")
        )
    path = os.path.join(base, APP_NAME)
    os.makedirs(path, exist_ok=True)
    return path


class SettingsStore:
    def __init__(self):
        self._dir = _config_dir()
        self._data = dict(DEFAULTS)
        self._dirty = set()      # какие группы изменились (для точечной записи)
        self._loaded = False

    # ---------- пути файлов ----------
    def _group_path(self, group):
        return os.path.join(self._dir, f"{group}.json")

    @property
    def path(self):
        # для обратной совместимости: путь основного файла
        return self._group_path("settings")

    # ---------- загрузка ----------
    def load(self):
        self._data = dict(DEFAULTS)

        # миграция: если новые файлы ещё не созданы, а старый монолит есть —
        # раскидать его по группам и сохранить.
        migrated = self._maybe_migrate()

        for group in GROUPS:
            self._load_group(group)

        if migrated:
            self.save_all()
        self._loaded = True
        return self._data

    def _load_group(self, group):
        path = self._group_path(group)
        try:
            with open(path, "r", encoding="utf-8") as f:
                saved = json.load(f)
            if isinstance(saved, dict):
                for k, v in saved.items():
                    if k in GROUPS[group]:
                        self._data[k] = v
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            pass  # нет файла/битый — остаются дефолты этой группы

    def _maybe_migrate(self):
        """Старый settings.json содержал ВСЕ ключи. Если новые файлы групп
        (commands/plugins/history) отсутствуют, а в settings.json лежат их
        данные — переносим их в память, чтобы затем сохранить по группам."""
        settings_path = self._group_path("settings")
        if not os.path.isfile(settings_path):
            return False
        # признак «старого» файла: наличие ключей из других групп внутри settings.json
        others_exist = any(
            os.path.isfile(self._group_path(g))
            for g in ("commands", "plugins", "history"))
        if others_exist:
            return False
        try:
            with open(settings_path, "r", encoding="utf-8") as f:
                old = json.load(f)
        except (json.JSONDecodeError, OSError):
            return False
        if not isinstance(old, dict):
            return False
        # есть ли в старом файле ключи не из группы settings?
        foreign = [k for k in old
                   if k in DEFAULTS and _KEY_TO_GROUP.get(k) != "settings"]
        if not foreign:
            return False
        # переносим все известные ключи в память
        for k, v in old.items():
            if k in DEFAULTS:
                self._data[k] = v
        return True

    # ---------- сохранение ----------
    def _save_group(self, group):
        path = self._group_path(group)
        payload = {k: self._data.get(k, DEFAULTS[k]) for k in GROUPS[group]}
        try:
            fd, tmp = tempfile.mkstemp(dir=self._dir, suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            os.replace(tmp, path)
            return True
        except OSError:
            return False

    def save(self):
        """Сохраняет только изменённые группы (или все, если неизвестно)."""
        groups = self._dirty or set(GROUPS.keys())
        ok = True
        for g in groups:
            ok = self._save_group(g) and ok
        self._dirty.clear()
        return ok

    def save_all(self):
        for g in GROUPS:
            self._save_group(g)
        self._dirty.clear()

    # ---------- доступ ----------
    def get(self, key, default=None):
        return self._data.get(key, DEFAULTS.get(key, default))

    def set(self, key, value):
        self._data[key] = value
        grp = _KEY_TO_GROUP.get(key)
        if grp:
            self._dirty.add(grp)

    def update(self, mapping: dict):
        for k, v in mapping.items():
            self.set(k, v)

    def all(self) -> dict:
        return dict(self._data)

    def reset(self, groups=("settings",)):
        """
        Сбрасывает к значениям по умолчанию только указанные группы.

        По умолчанию сбрасываются ТОЛЬКО пользовательские настройки
        (группа "settings"): тема, поведение окна, голос, приватность и т.д.
        Пользовательские команды, история и плагины сохраняются — их удаление
        должно быть отдельным осознанным действием, а не побочным эффектом
        «Сбросить настройки».
        """
        for grp in groups:
            for k in GROUPS.get(grp, {}):
                self._data[k] = DEFAULTS[k]
            self._dirty.add(grp)
        self.save()

    def reset_all(self):
        """Полный заводской сброс: обнуляет ВСЕ группы (команды, историю и т.д.)."""
        self._data = dict(DEFAULTS)
        self.save_all()


# единый экземпляр на всё приложение
settings = SettingsStore()
