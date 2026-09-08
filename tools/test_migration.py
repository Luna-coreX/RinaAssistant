# -*- coding: utf-8 -*-
"""
I02: 3.0.0's data survives the move, and there is somewhere to go back to.

Plan item 4.0-I02. The migration was written together with the splitting
of the files and has not been checked once since — and this is code that
runs **once, on somebody else's machine**, and silently. A fault in it does
not look like a fault: a person starts the new version and sees the default
settings, an empty list of commands and a clean history. Putting that down
to "I reinstalled" is easier than finding the cause.

A 3.0.0 config is one file with everything at once: settings, commands,
plugins, history, reminders. It has no format version, because back then
none was written; the recognition language lies in a separate `language`
key, and the learned programs are path strings rather than records.

Three things are checked, and the third is the one for whose sake the item
is marked "mandatory":

    1. nothing is lost: five groups went off into their files, the values
       are intact;
    2. the shape is brought up to the present: the language was carried
       over, the program records were lifted;
    3. **there is somewhere to go back to**: the backup was taken before
       the edits and holds the original.

The store works in a temporary directory: a migration check that migrates
the person's real settings is exactly the trouble it is supposed to guard
against.

To run:
    python tools/test_migration.py
"""
import io
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
os.chdir(ROOT)

from console import use_utf8
use_utf8()

fails = 0


def check(label, cond, detail=""):
    global fails
    if not cond:
        fails += 1
    print(("OK   " if cond else "FAIL "), label, detail)


#: A config in 3.0.0 shape: one file, everything together, no format
#: version.
#:
#: The values are chosen to differ from the defaults: a setting that
#: matches the factory one is indistinguishable from a lost one, and a
#: check on it is always green.
LEGACY = {
    "voice": "ru-RU-SvetlanaNeural",
    "volume": 42,
    "speed": 115,
    "tts_engine": "edge",
    "stt_engine": "vosk",
    "wake_words": ["Рина", "Рина, милая"],
    "hotkey": "Ctrl+Alt+Z",
    "search_engine": "duckduckgo",

    # A 3.0.0 key: the recognition language lived separately from the
    # interface language.
    "language": "English",

    # The learned programs as path strings (the shape before v2).
    "app_aliases": {
        "ренпай": r"C:\Games\RenPy\renpy.exe",
        "студия": r"D:\Tools\Studio\studio.exe",
    },

    # The data that accumulated over years and hurts most to lose.
    "custom_commands": [
        {"id": "cmd_a1", "enabled": True, "type": "app",
         "triggers": ["запусти блокнот"], "target": "notepad.exe"},
        {"id": "cmd_b2", "enabled": False, "type": "website",
         "triggers": ["открой почту"], "target": "https://mail.example"},
    ],
    "command_stats": {"cmd_a1": 17},
    "enabled_plugins": ["clock", "notes"],
    "plugin_settings": {"notes": {"items": ["купить хлеб"], "limit": 50}},
    "history": [
        {"ts": 1700000000.0, "kind": "user", "text": "который час",
         "source": "voice"},
        {"ts": 1700000001.0, "kind": "assistant", "text": "Сейчас 14:05"},
    ],
    "reminders": [
        {"id": "rem_1", "kind": "timer", "fire_at": 4102444800.0,
         "text": "чайник", "done": False},
    ],
}


def make_legacy(where):
    """Put a 3.0.0 config down the way it lay on the person's machine."""
    os.makedirs(where, exist_ok=True)
    with io.open(os.path.join(where, "settings.json"), "w",
                 encoding="utf-8") as f:
        json.dump(LEGACY, f, ensure_ascii=False, indent=2)


def fresh_store(data_dir):
    """
    A store looking into a stand-in directory.

    The modules are reloaded: the directory is computed on first access and
    remembered, and a second store in the same process would look where the
    first one looks.
    """
    os.environ["APPDATA"] = data_dir
    for name in list(sys.modules):
        if name.startswith("core."):
            del sys.modules[name]
    import importlib
    store_mod = importlib.import_module("core.settings_store")
    return store_mod, store_mod.SettingsStore()


home = tempfile.mkdtemp(prefix="rina-migration-")
data = os.path.join(home, "RinaAssistant")
make_legacy(data)
before = io.open(os.path.join(data, "settings.json"), encoding="utf-8").read()

module, store = fresh_store(home)
store.load()


print("=== ничего не потеряно ===")

check("громкость дожила", store.get("volume") == 42, f"| {store.get('volume')}")
check("движок синтеза дожил", store.get("tts_engine") == "edge",
      f"| {store.get('tts_engine')}")
check("слова активации дожили",
      store.get("wake_words") == ["Рина", "Рина, милая"],
      f"| {store.get('wake_words')}")
check("сочетание клавиш дожило", store.get("hotkey") == "Ctrl+Alt+Z",
      f"| {store.get('hotkey')}")

commands = store.get("custom_commands") or []
check("команды дожили все", len(commands) == 2, f"| {len(commands)}")
check("и выключенная осталась выключенной",
      any(c.get("id") == "cmd_b2" and not c.get("enabled") for c in commands),
      f"| {[c.get('enabled') for c in commands]}")
check("статистика запусков дожила",
      (store.get("command_stats") or {}).get("cmd_a1") == 17,
      f"| {store.get('command_stats')}")

check("включённые плагины дожили",
      store.get("enabled_plugins") == ["clock", "notes"],
      f"| {store.get('enabled_plugins')}")
check("настройки плагина дожили",
      (store.get("plugin_settings") or {}).get("notes", {}).get("items")
      == ["купить хлеб"], f"| {store.get('plugin_settings')}")

check("история дожила", len(store.get("history") or []) == 2,
      f"| {len(store.get('history') or [])}")
check("напоминания дожили", len(store.get("reminders") or []) == 1,
      f"| {len(store.get('reminders') or [])}")


print()
print("=== форма приведена к нынешней ===")

check("версия формата записана",
      store.get("config_version") == module.CONFIG_VERSION,
      f"| {store.get('config_version')}")

# The 3.0.0 recognition language must not silently move to another one:
# the person chose it, and the merged setting defaults to Russian.
check("язык распознавания перенесён в язык интерфейса",
      store.get("ui_language") == "English", f"| {store.get('ui_language')}")

aliases = store.get("app_aliases") or {}
check("выученные программы стали записями",
      all(isinstance(v, dict) and v.get("path") for v in aliases.values()),
      f"| {aliases}")
check("и имя у записи осмысленное",
      aliases.get("ренпай", {}).get("name") == "renpy",
      f"| {aliases.get('ренпай')}")

for group in ("settings", "commands", "plugins", "history", "reminders"):
    path = os.path.join(data, f"{group}.json")
    check(f"файл группы «{group}» появился", os.path.isfile(path))


print()
print("=== есть куда вернуться ===")

backup = os.path.join(data, "backup-v0")
check("копия сделана", os.path.isdir(backup), f"| {backup}")

saved = os.path.join(backup, "settings.json")
if os.path.isfile(saved):
    # The backup must hold **the original**, not what has already been
    # rewritten: a backup taken after the edit is not a backup but a second
    # helping of the same thing.
    check("в копии лежит исходный конфиг",
          io.open(saved, encoding="utf-8").read() == before,
          "| копия снята после правок")
else:
    check("в копии лежит исходный конфиг", False, "| файла нет")

restored = getattr(store, "restore_backup", None)
check("хранилище умеет откатиться", callable(restored),
      "| «обязательно с бэкапом и возможностью откатиться» (4.0-I02)")

if callable(restored):
    store.set("volume", 3)
    store.save()
    ok = store.restore_backup()
    check("откат состоялся", ok)

    # We look at the disk **before** loading: loading migrates again and
    # will rewrite the files. Checking after it would mean checking the
    # migration rather than the rollback.
    after = io.open(os.path.join(data, "settings.json"),
                    encoding="utf-8").read()
    check("на диске снова исходный конфиг", after == before,
          "| откат обязан вернуть форму, а не только значения")
    check("файлов, которых у 3.0.0 не было, не осталось",
          not os.path.isfile(os.path.join(data, "commands.json")),
          "| иначе на диске смесь, какой ни одна версия не писала")

    # What was displaced is set aside, not erased: a rollback that
    # destroys what it replaces is itself irreversible.
    aside = os.path.join(backup, "replaced", "settings.json")
    check("замещённое отложено", os.path.isfile(aside), f"| {aside}")
    if os.path.isfile(aside):
        put = json.load(io.open(aside, encoding="utf-8"))
        check("и это именно то, что заменили", put.get("volume") == 3,
              f"| {put.get('volume')}")

    # And now that it can actually be used: a new core comes up on the
    # restored config and migrates it again, as if for the first time.
    module2, store2 = fresh_store(home)
    store2.load()
    check("на возвращённом конфиге всё снова поднимается",
          store2.get("volume") == 42
          and len(store2.get("custom_commands") or []) == 2,
          f"| громкость {store2.get('volume')}, "
          f"команд {len(store2.get('custom_commands') or [])}")

print()
print("=== позвать откат может человек, а не только код ===")

# A method that cannot be called is not the ability to roll back. We check
# it the same way a person would: by starting the core with the flag.
import subprocess
from console import child_env


def core_says(*flags):
    done = subprocess.run(
        [sys.executable, "rina_core.py", *flags],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=dict(child_env(), APPDATA=home), timeout=60)
    return done.returncode, (done.stdout or "") + (done.stderr or "")

code, said = core_says("--list-backups")
check("ядро показывает, что есть", code == 0 and "backup-v0" in said,
      f"| {said.strip().splitlines()[-1:]}")

code, said = core_says("--restore-backup", "7")
check("несуществующую копию не выдумывает",
      code != 0 and "нет" in said, f"| {said.strip()}")

code, said = core_says("--restore-backup")
check("откат по ключу срабатывает", code == 0 and "вернули" in said,
      f"| {said.strip().splitlines()[:1]}")
# And it says where what was displaced went: otherwise a person who rolled
# back by mistake will decide they lost everything accumulated since the
# migration.
check("и сказано, куда отложено замещённое", "replaced" in said,
      f"| {said.strip()}")

print()
print("=== возвращаться некуда ===")

# The commonest case: there was no migration at all. The rollback must
# answer "no" rather than fall over or pretend it worked: a person will
# read either of those as "restored" while nothing was restored.
clean_home = tempfile.mkdtemp(prefix="rina-nomigration-")
_, untouched = fresh_store(clean_home)
untouched.load()
check("без копий откат честно отвечает «нет»",
      untouched.restore_backup() is False)
check("и копий действительно нет", untouched.backups() == [],
      f"| {untouched.backups()}")

shutil.rmtree(clean_home, ignore_errors=True)
shutil.rmtree(home, ignore_errors=True)

print()
print("ИТОГО ошибок:", fails)
sys.exit(1 if fails else 0)
