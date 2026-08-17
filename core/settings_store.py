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

# Версия схемы конфига. Растёт, когда меняется ФОРМА данных (а не набор
# настроек): добавление нового ключа с дефолтом миграции не требует.
#   0 — конфиги до 2.0 (версия не записывалась)
#   1 — язык распознавания объединён с языком интерфейса (ui_language)
#   2 — app_aliases хранит словарь {path, kind, name}, а не строку пути
CONFIG_VERSION = 2


# Значения по умолчанию, сгруппированные по файлам.
GROUPS = {
    "settings": {
        # --- страница «Рина» ---
        "voice": "default",
        "wake_word": "Рина",
        "wake_words": ["Рина", "Rina"],
        "volume": 75,
        "speed": 100,
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
        "search_engine": "google",
        "web_search_fallback": True,
        "program_folders": [],
        "app_aliases": {},
        "wake_sensitivity": 0.8,
        "listen_seconds": 8,
        "config_version": 0,
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
    "reminders": {
        "reminders": [],
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


def config_dir() -> str:
    """Папка с данными приложения (настройки, кэши). Создаётся при обращении."""
    return _config_dir()


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

        # обновление формы данных до текущей версии схемы
        migrated = self._migrate_schema() or migrated

        if migrated:
            self.save_all()
        self._loaded = True
        return self._data

    # ---------- миграция схемы ----------
    def _raw_group(self, group):
        """Сырое содержимое файла группы (включая ключи, которых уже нет)."""
        try:
            with open(self._group_path(group), "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _backup_config(self, from_version):
        """
        Копия конфигов перед первой миграцией.

        Пользовательские команды и история накапливаются годами — если
        миграция окажется неудачной, должно остаться к чему вернуться.
        """
        backup_dir = os.path.join(self._dir, f"backup-v{from_version}")
        if os.path.isdir(backup_dir):
            return          # копия уже есть, второй раз не перезаписываем
        try:
            os.makedirs(backup_dir, exist_ok=True)
            for group in GROUPS:
                src = self._group_path(group)
                if os.path.isfile(src):
                    with open(src, "r", encoding="utf-8") as f:
                        content = f.read()
                    with open(os.path.join(backup_dir, f"{group}.json"),
                              "w", encoding="utf-8") as f:
                        f.write(content)
        except OSError:
            pass            # не смогли сделать копию — миграцию всё равно проводим

    def _migrate_schema(self):
        """Приводит данные к текущей CONFIG_VERSION. True, если что-то меняли."""
        stored = self._data.get("config_version", 0)
        try:
            stored = int(stored)
        except (TypeError, ValueError):
            stored = 0
        if stored >= CONFIG_VERSION:
            return False

        # конфиг существует (а не создаётся с нуля) — бэкапим перед правками
        if os.path.isfile(self._group_path("settings")):
            self._backup_config(stored)

        if stored < 1:
            self._migrate_to_v1()
        if stored < 2:
            self._migrate_to_v2()

        self._data["config_version"] = CONFIG_VERSION
        return True

    def _migrate_to_v1(self):
        """
        Язык распознавания речи объединён с языком интерфейса.

        Раньше «Язык» на вкладке Рины (ключ language) управлял только
        распознаванием. Если пользователь его менял, а язык интерфейса не
        трогал — переносим его выбор, чтобы распознавание не «переехало»
        молча на другой язык.
        """
        old = self._raw_group("settings")
        legacy_lang = str(old.get("language", "")).strip()
        if not legacy_lang:
            return
        from core.i18n import LANGUAGES
        if (legacy_lang in LANGUAGES
                and self._data.get("ui_language") == DEFAULTS["ui_language"]):
            self._data["ui_language"] = legacy_lang

    def _migrate_to_v2(self):
        """app_aliases: строка с путём -> словарь {path, kind, name}."""
        aliases = self._data.get("app_aliases") or {}
        if not isinstance(aliases, dict):
            self._data["app_aliases"] = {}
            return
        upgraded = {}
        for key, value in aliases.items():
            if isinstance(value, str):
                name = os.path.splitext(os.path.basename(value))[0]
                upgraded[key] = {"path": value, "kind": "file", "name": name}
            elif isinstance(value, dict) and value.get("path"):
                upgraded[key] = value
            # прочее (битые записи) отбрасываем
        self._data["app_aliases"] = upgraded

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
