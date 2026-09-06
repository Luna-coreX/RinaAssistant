# -*- coding: utf-8 -*-
"""
I02: данные 3.0.0 переживают переезд, и есть куда вернуться.

Задача плана 4.0-I02. Миграция была написана вместе с разделением файлов и с
тех пор не проверялась ни разу — а это тот код, который выполняется **один
раз на чужой машине** и молча. Ошибка в нём выглядит не как ошибка: человек
запускает новую версию и видит настройки по умолчанию, пустой список команд
и чистую историю. Списать это на «переустановил» проще, чем найти причину.

Конфиг 3.0.0 — один файл со всем сразу: настройки, команды, плагины,
история, напоминания. Версии формата в нём нет, потому что тогда её ещё не
записывали; язык распознавания лежит отдельным ключом `language`, а
выученные программы — строками пути, а не записями.

Проверяется три вещи, и третья — та, ради которой задача помечена
«обязательно»:

    1. ничего не потеряно: пять групп разъехались по файлам, значения целы;
    2. форма приведена к нынешней: язык перенесён, записи программ подняты;
    3. **есть куда вернуться**: копия сделана до правок и содержит исходное.

Хранилище работает во временном каталоге: проверка миграции, которая
мигрирует настоящие настройки человека, — это ровно та беда, от которой она
должна защищать.

Запуск:
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


#: Конфиг в форме 3.0.0: один файл, всё вместе, версии формата нет.
#:
#: Значения выбраны так, чтобы отличались от умолчаний: настройка, совпавшая
#: с заводской, не отличима от потерянной, и проверка на ней всегда зелёная.
LEGACY = {
    "voice": "ru-RU-SvetlanaNeural",
    "volume": 42,
    "speed": 115,
    "tts_engine": "edge",
    "stt_engine": "vosk",
    "wake_words": ["Рина", "Рина, милая"],
    "hotkey": "Ctrl+Alt+Z",
    "search_engine": "duckduckgo",

    # Ключ 3.0.0: язык распознавания жил отдельно от языка интерфейса.
    "language": "English",

    # Выученные программы — строками пути (форма до v2).
    "app_aliases": {
        "ренпай": r"C:\Games\RenPy\renpy.exe",
        "студия": r"D:\Tools\Studio\studio.exe",
    },

    # Данные, которые накапливались годами и терять которые больнее всего.
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
    """Положить конфиг 3.0.0 так, как он лежал у человека."""
    os.makedirs(where, exist_ok=True)
    with io.open(os.path.join(where, "settings.json"), "w",
                 encoding="utf-8") as f:
        json.dump(LEGACY, f, ensure_ascii=False, indent=2)


def fresh_store(data_dir):
    """
    Хранилище, смотрящее в подставной каталог.

    Модули перезагружаются: каталог вычисляется при первом обращении и
    запоминается, и второе хранилище в том же процессе смотрело бы туда же,
    куда первое.
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

# Язык распознавания 3.0.0 не должен молча переехать на другой: человек его
# выбирал, а объединённая настройка по умолчанию русская.
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
    # Копия обязана содержать **исходное**, а не уже переписанное: копия,
    # снятая после правки, — это не копия, а вторая порция того же.
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

    # Смотрим на диск **до** загрузки: загрузка мигрирует заново и перепишет
    # файлы. Проверять после неё значило бы проверять миграцию, а не откат.
    after = io.open(os.path.join(data, "settings.json"),
                    encoding="utf-8").read()
    check("на диске снова исходный конфиг", after == before,
          "| откат обязан вернуть форму, а не только значения")
    check("файлов, которых у 3.0.0 не было, не осталось",
          not os.path.isfile(os.path.join(data, "commands.json")),
          "| иначе на диске смесь, какой ни одна версия не писала")

    # Замещённое отложено, а не стёрто: откат, уничтожающий то, что он
    # заменяет, сам необратим.
    aside = os.path.join(backup, "replaced", "settings.json")
    check("замещённое отложено", os.path.isfile(aside), f"| {aside}")
    if os.path.isfile(aside):
        put = json.load(io.open(aside, encoding="utf-8"))
        check("и это именно то, что заменили", put.get("volume") == 3,
              f"| {put.get('volume')}")

    # А теперь — что этим можно пользоваться: новое ядро поднимается на
    # возвращённом конфиге и мигрирует его заново, как в первый раз.
    module2, store2 = fresh_store(home)
    store2.load()
    check("на возвращённом конфиге всё снова поднимается",
          store2.get("volume") == 42
          and len(store2.get("custom_commands") or []) == 2,
          f"| громкость {store2.get('volume')}, "
          f"команд {len(store2.get('custom_commands') or [])}")

print()
print("=== позвать откат может человек, а не только код ===")

# Метод, который нельзя позвать, — это не возможность откатиться. Проверяем
# тем же способом, каким это сделает человек: запуском ядра с ключом.
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
# И говорит, куда делось замещённое: человек, откатившийся по ошибке, иначе
# решит, что потерял всё, что накопил после миграции.
check("и сказано, куда отложено замещённое", "replaced" in said,
      f"| {said.strip()}")

print()
print("=== возвращаться некуда ===")

# Самый частый случай: миграции не было вовсе. Откат обязан ответить «нет»,
# а не упасть и не сделать вид, что получилось: и то и другое человек
# прочитает как «вернули», ничего не вернув.
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
