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

import contextlib
import copy
import os
import sys
import json
import tempfile
import threading


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
        # Отделка 4.0 (4.0-R08, F07). Две равноправные, и «чёрное» здесь не
    # потому, что лучше, а потому, что все пять палитр 3.1.0 были тёмными:
    # человек, обновившийся с 3.1.0, увидит то же, что видел вчера.
    "finish": "black",
    # Тема и акцент 3.1.0 остаются в хранилище, но больше не участвуют:
    # дизайн-система заменила пять заимствованных палитр двумя отделками.
    # Стереть их значило бы уничтожить данные ради опрятности файла.
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
        # локальная языковая модель (Ollama). Выключена по умолчанию:
        # это тяжёлая возможность, которая требует установленного сервера.
        "llm_enabled": False,
        "llm_url": "http://localhost:11434",
        "llm_model": "",
        "llm_persona": "",
        "llm_timeout": 30,
        # журналирование. Тексты реплик — содержимое разговора, поэтому
        # пишутся только при явном согласии и только на уровне DEBUG.
        "log_level": "INFO",
        "log_texts": False,
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
#
# ВАЖНО: половина значений здесь — изменяемые (списки и словари), и они
# общие с GROUPS. Копировать их можно только глубоко: поверхностная копия
# отдавала бы приложению тот же самый объект, и первая же настройка плагина
# меняла бы «значение по умолчанию». Для этого есть defaults_for().
DEFAULTS = {}
for _grp in GROUPS.values():
    DEFAULTS.update(_grp)

# Обратный индекс: ключ -> имя файла/группы.
_KEY_TO_GROUP = {}
for _name, _grp in GROUPS.items():
    for _k in _grp:
        _KEY_TO_GROUP[_k] = _name


def default_value(key):
    """Заводское значение ключа — всегда отдельный объект."""
    return copy.deepcopy(DEFAULTS[key])


def defaults_for(group=None):
    """Заводские значения группы (или все) — всегда отдельные объекты."""
    source = GROUPS[group] if group is not None else DEFAULTS
    return copy.deepcopy(source)


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
        # к настройкам обращаются из нескольких потоков (см. save)
        self._lock = threading.RLock()
        self._dir = _config_dir()
        self._data = defaults_for()
        self._dirty = set()      # какие группы изменились (для точечной записи)
        self._loaded = False
        self._loading = False

    # ---------- атомарные изменения ----------
    @contextlib.contextmanager
    def transaction(self):
        """
        Блокировка на всю последовательность «прочитать — изменить — записать».

        set() и save() по отдельности потокобезопасны, а такая
        последовательность — нет: два потока читают одно состояние, и второй
        затирает изменения первого. Так пропадали записи истории, когда ответ
        Рины и сработавшее напоминание писались одновременно.

        Блокировка та же самая (RLock), поэтому вложенные set()/save()
        внутри блока работают как обычно.
        """
        with self._lock:
            yield self

    # ---------- пути файлов ----------
    def _group_path(self, group):
        return os.path.join(self._dir, f"{group}.json")

    @property
    def path(self):
        # для обратной совместимости: путь основного файла
        return self._group_path("settings")

    # ---------- загрузка ----------
    def load(self):
        self._data = defaults_for()

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
        except OSError as e:
            # молчаливая потеря настроек — худший из отказов: пользователь
            # думает, что сохранил, а после перезапуска всё вернулось
            from core.logging_setup import get_logger
            get_logger("settings").error(
                "Не удалось записать группу «%s» в %s: %s", group, path, e)
            return False

    def save(self):
        """
        Сохраняет только изменённые группы (или все, если неизвестно).

        **Записывать можно только прочитанное.** Хранилище, которое не
        читали, держит умолчания, и запись затирает файл человека ими —
        причём не тем ключом, который меняли, а всей группой целиком. Так и
        пропали настройки: ядро не звало `load()`, оболочка записала одну
        отделку, и вместе с ней на диск уехали умолчания вместо голоса,
        движка распознавания и темы.
        """
        self._ensure_loaded()
        # Настройки пишут несколько потоков сразу: команда из окна, ответ из
        # потока распознавания, сработавшее напоминание. Раньше save() шёл
        # прямо по self._dirty, и добавление ключа в другом потоке роняло
        # перебор («Set changed size during iteration»).
        with self._lock:
            groups = set(self._dirty) if self._dirty else set(GROUPS.keys())
            self._dirty.clear()
            ok = True
            for g in groups:
                ok = self._save_group(g) and ok
            return ok

    def save_all(self):
        self._ensure_loaded()
        with self._lock:
            for g in GROUPS:
                self._save_group(g)
            self._dirty.clear()

    # ---------- доступ ----------
    def _ensure_loaded(self):
        """
        Прочитать файлы, если этого ещё никто не сделал.

        Загрузка была обязанностью того, кто первым обратится, — и в 3.1.0
        это делало окно, единственный вход в программу. В 4.0 входов стало
        два: окно уехало в другой процесс, а ядро запускается само. Ядро
        `load()` не звало, и работало на умолчаниях: настройки читались не
        те, что человек когда-то выбрал, а записывались поверх его файла.

        Поэтому загрузка теперь не поручение, а свойство хранилища: первое
        же обращение её вызывает. Забыть нельзя.
        """
        with self._lock:
            if self._loaded or self._loading:
                return
            self._loading = True
            try:
                self.load()
            finally:
                self._loading = False

    def get(self, key, default=None):
        self._ensure_loaded()
        return self._data.get(key, DEFAULTS.get(key, default))

    def set(self, key, value):
        # Записать, не прочитав, значило бы затереть файл умолчаниями.
        self._ensure_loaded()
        with self._lock:
            self._data[key] = value
            grp = _KEY_TO_GROUP.get(key)
            if grp:
                self._dirty.add(grp)

    def update(self, mapping: dict):
        for k, v in mapping.items():
            self.set(k, v)

    def all(self) -> dict:
        self._ensure_loaded()
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
                self._data[k] = default_value(k)
            self._dirty.add(grp)
        self.save()

    def reset_all(self):
        """Полный заводской сброс: обнуляет ВСЕ группы (команды, историю и т.д.)."""
        self._data = defaults_for()
        self.save_all()


# единый экземпляр на всё приложение
settings = SettingsStore()
