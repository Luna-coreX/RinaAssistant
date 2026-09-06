"""
The application's settings store — split across several files.

Physically the data lies in several JSON files in the user's folder:
  Windows: %APPDATA%/RinaAssistant/
  Linux:   ~/.config/RinaAssistant/
  macOS:   ~/Library/Application Support/RinaAssistant/

The files:
  settings.json  — the application's settings and the "Rina" page
  commands.json  — the user's commands and launch statistics
  plugins.json   — switched-on plugins and their settings
  history.json   — the journal of interactions

From outside this is still ONE `settings` object with get/set/save — code
that reads settings.get("history") and the like need not change. The routing
of a key into the right file happens inside. On the first start after an
update, the old monolithic settings.json migrates into the new files
automatically.
"""

import contextlib
import copy
import os
import re
import shutil
import sys
import json
import tempfile
import threading


APP_NAME = "RinaAssistant"

# The config schema's version. It grows when the SHAPE of the data changes
# (not the set of settings): adding a new key with a default needs no
# migration.
#   0 — configs before 2.0 (the version was not written down)
#   1 — the recognition language merged with the interface language (ui_language)
#   2 — app_aliases stores a dict {path, kind, name} rather than a path string
CONFIG_VERSION = 2


# Default values, grouped by file.
GROUPS = {
    "settings": {
        # --- the "Rina" page ---
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
        # --- the application ---
        # The 4.0 finish (4.0-R08, F07). Two equals, and "black" here is not
    # because it is better but because all five 3.1.0 palettes were dark: a
    # person upgrading from 3.1.0 will see what they saw yesterday.
    "finish": "black",
    # 3.1.0's theme and accent stay in the store but no longer take part:
    # the design system replaced five borrowed palettes with two finishes.
    # Erasing them would mean destroying data for the sake of a tidy file.
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
        # the local language model (Ollama). Off by default: this is a heavy
        # capability that requires an installed server.
        "llm_enabled": False,
        "llm_url": "http://localhost:11434",
        "llm_model": "",
        "llm_persona": "",
        "llm_timeout": 30,
        # journalling. The text of lines is the content of a conversation, so
        # it is written only with explicit consent and only at DEBUG level.
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

# A flat dictionary of every default (for API backward compatibility).
#
# IMPORTANT: half the values here are mutable (lists and dicts), and they are
# shared with GROUPS. They may only be copied deeply: a shallow copy would
# hand the application the very same object, and the first plugin setting
# would change the "default value". That is what defaults_for() is for.
DEFAULTS = {}
for _grp in GROUPS.values():
    DEFAULTS.update(_grp)

# The reverse index: key -> file/group name.
_KEY_TO_GROUP = {}
for _name, _grp in GROUPS.items():
    for _k in _grp:
        _KEY_TO_GROUP[_k] = _name


def default_value(key):
    """A key's factory value — always a separate object."""
    return copy.deepcopy(DEFAULTS[key])


def defaults_for(group=None):
    """A group's factory values (or all of them) — always separate objects."""
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
    """The folder with the application's data (settings, caches). Created on demand."""
    return _config_dir()


class SettingsStore:
    def __init__(self):
        # the settings are accessed from several threads (see save)
        self._lock = threading.RLock()
        self._dir = _config_dir()
        self._data = defaults_for()
        self._dirty = set()      # which groups changed (for a targeted write)
        self._loaded = False
        self._loading = False

    # ---------- atomic changes ----------
    @contextlib.contextmanager
    def transaction(self):
        """
        A lock over the whole "read — change — write" sequence.

        set() and save() are thread-safe separately, but such a sequence is
        not: two threads read one state, and the second overwrites the
        first's changes. That is how history entries went missing when
        Rina's answer and a fired reminder were written at the same time.

        The lock is the same one (RLock), so nested set()/save() inside the
        block work as usual.
        """
        with self._lock:
            yield self

    # ---------- file paths ----------
    def _group_path(self, group):
        return os.path.join(self._dir, f"{group}.json")

    @property
    def path(self):
        # for backward compatibility: the path of the main file
        return self._group_path("settings")

    # ---------- loading ----------
    def load(self):
        self._data = defaults_for()

        # migration: if the new files have not been created yet and the old
        # monolith exists — scatter it across the groups and save.
        migrated = self._maybe_migrate()

        for group in GROUPS:
            self._load_group(group)

        # bringing the data's shape up to the current schema version
        migrated = self._migrate_schema() or migrated

        if migrated:
            self.save_all()
        self._loaded = True
        return self._data

    # ---------- schema migration ----------
    def _raw_group(self, group):
        """The raw content of a group's file (including keys that no longer exist)."""
        try:
            with open(self._group_path(group), "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _backup_config(self, from_version):
        """
        A copy of the configs before the first migration.

        The user's commands and history accumulate over years — if the
        migration turns out badly, there must be something to go back to.
        """
        backup_dir = os.path.join(self._dir, f"backup-v{from_version}")
        if os.path.isdir(backup_dir):
            return          # the copy already exists; we do not overwrite it twice
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
            pass            # could not make a copy: we migrate all the same

    def backups(self):
        """
        Which copies exist, oldest first. The number is the version they were
        taken from.
        """
        found = []
        try:
            for name in os.listdir(self._dir):
                match = re.fullmatch(r"backup-v(\d+)", name)
                if match and os.path.isdir(os.path.join(self._dir, name)):
                    found.append(int(match.group(1)))
        except OSError:
            return []
        return sorted(found)

    def restore_backup(self, from_version=None):
        """
        Put the files back as they were before a migration. `True` if done.

        The copy has been taken since the file split and never read: a backup
        nobody can restore from is a folder that takes up room. Plan item
        `4.0-I02` asks for both halves, and this is the second.

        **The newest copy by default.** The one taken from the highest
        version is the state just before the last migration — that is what a
        person wants back when a migration turned out badly.

        **Files the copy does not have are deleted.** A restore that only
        overwrites leaves a mixed state: the old monolith plus the new group
        files, which no version of the program ever wrote. What has to come
        back is the shape, not only the values.

        **What is replaced is put aside first, and once.** A rollback that
        destroys the state it replaces is itself irreversible, and this is
        the wrong place for that. It is put aside once, by the same rule as
        the copy itself: a second rollback would otherwise overwrite the
        valuable state with the one just restored.
        """
        with self._lock:
            available = self.backups()
            if not available:
                return False
            version = available[-1] if from_version is None else from_version
            source = os.path.join(self._dir, f"backup-v{version}")
            if not os.path.isdir(source):
                return False

            try:
                aside = os.path.join(source, "replaced")
                if not os.path.isdir(aside):
                    os.makedirs(aside, exist_ok=True)
                    for group in GROUPS:
                        current = self._group_path(group)
                        if os.path.isfile(current):
                            shutil.copy2(current,
                                         os.path.join(aside, f"{group}.json"))

                for group in GROUPS:
                    current = self._group_path(group)
                    if os.path.isfile(current):
                        os.remove(current)
                for name in os.listdir(source):
                    if not name.endswith(".json"):
                        continue
                    shutil.copy2(os.path.join(source, name),
                                 os.path.join(self._dir, name))
            except OSError:
                return False

            # What is in memory is now a stranger to what is on disk, and
            # the next `save()` would write it back over the restored files.
            self._data = defaults_for()
            self._dirty.clear()
            self._loaded = False
            return True

    def _migrate_schema(self):
        """Brings the data up to the current CONFIG_VERSION. True if anything was changed."""
        stored = self._data.get("config_version", 0)
        try:
            stored = int(stored)
        except (TypeError, ValueError):
            stored = 0
        if stored >= CONFIG_VERSION:
            return False

        # the config exists (rather than being created from scratch) — we back it up before editing
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
        The speech recognition language has been merged with the interface
        language.

        Previously "Language" on Rina's tab (the `language` key) governed
        recognition alone. If the user changed it and left the interface
        language alone, we carry their choice over, so that recognition does
        not silently "move" to another language.
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
        """app_aliases: a path string -> a dict {path, kind, name}."""
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
            # the rest (broken entries) we discard
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
            pass  # no file or a broken one: this group's defaults remain

    def _maybe_migrate(self):
        """The old settings.json contained EVERY key. If the new group files
        (commands/plugins/history) are absent and settings.json holds their
        data — we carry it into memory, to save it by group afterwards."""
        settings_path = self._group_path("settings")
        if not os.path.isfile(settings_path):
            return False
        # the mark of an "old" file: keys from other groups present inside settings.json
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
        # are there keys in the old file that are not from the settings group?
        foreign = [k for k in old
                   if k in DEFAULTS and _KEY_TO_GROUP.get(k) != "settings"]
        if not foreign:
            return False
        # we carry every known key into memory
        for k, v in old.items():
            if k in DEFAULTS:
                self._data[k] = v
        return True

    # ---------- saving ----------
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
            # a silent loss of settings is the worst of failures: the user
            # thinks they saved, and after a restart everything is back
            from core.logging_setup import get_logger
            get_logger("settings").error(
                "Не удалось записать группу «%s» в %s: %s", group, path, e)
            return False

    def save(self):
        """
        Saves only the groups that changed (or all, if that is unknown).

        **Only what has been read may be written.** A store that has not
        been read holds the defaults, and a write overwrites a person's file
        with them — and not by the key that was changed but by the whole
        group. That is how the settings went missing: the core did not call
        `load()`, the shell wrote down one finish, and along with it the
        defaults went to disk instead of the voice, the recognition engine
        and the theme.
        """
        self._ensure_loaded()
        # Several threads write settings at once: a command from the
        # window, an answer from the recognition thread, a fired reminder.
        # save() used to walk self._dirty directly, and adding a key in
        # another thread dropped the walk ("Set changed size during
        # iteration").
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

    # ---------- access ----------
    def _ensure_loaded(self):
        """
        Read the files, if nobody has done so yet.

        Loading used to be the duty of whoever accessed the store first —
        and in 3.1.0 that was the window, the program's only entrance. In
        4.0 there are two entrances: the window moved to another process,
        and the core starts by itself. The core did not call `load()` and
        worked on the defaults: the settings read were not the ones the
        person had once chosen, and they were written over their file.

        So loading is no longer an errand but a property of the store: the
        very first access brings it about. It cannot be forgotten.
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
        # Writing without having read would mean overwriting the file with defaults.
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
        Resets only the groups named to their default values.

        By default ONLY the user's settings are reset (the "settings"
        group): the theme, the window's behaviour, the voice, privacy and so
        on. The user's commands, history and plugins are kept — deleting
        those must be a separate deliberate action rather than a side effect
        of "Reset settings".
        """
        for grp in groups:
            for k in GROUPS.get(grp, {}):
                self._data[k] = default_value(k)
            self._dirty.add(grp)
        self.save()

    def reset_all(self):
        """A full factory reset: zeroes EVERY group (commands, history and so on)."""
        self._data = defaults_for()
        self.save_all()


# one instance for the whole application
settings = SettingsStore()
