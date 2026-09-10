# -*- coding: utf-8 -*-
"""
4.0b-B01: the inventory of what is kept about a person.

**The assertion that matters is the last one.** A privacy page that can
quietly go out of date is worse than no page: on the day a new kind of
personal data starts being kept, a hand-maintained list goes on answering
"this is everything" — a lie told by the one screen a person opens in order
to be told the truth. So a key nobody has claimed must turn up in the
inventory **by itself**, and that is checked by adding one.

The rest is ordinary: what is stored is what is shown, and content nobody
put there does not appear out of nowhere.
"""
import os
import sys

sys.path.insert(0, r"C:\DevStation\PCDev\DesktopApps\RinaAssistant")
sys.path.insert(0, os.path.join(
    r"C:\DevStation\PCDev\DesktopApps\RinaAssistant", "tools"))

from console import use_utf8
from core import privacy, settings_schema
from core.settings_api import MemorySettings

use_utf8()

fails = 0


def check(label, cond, detail=""):
    global fails
    if not cond:
        fails += 1
    print(("OK   " if cond else "FAIL "), label, detail)


def group(groups, name):
    for one in groups:
        if one["id"] == name:
            return one
    return None


def said(groups, name):
    found = group(groups, name)
    return [item["what"] for item in (found or {}).get("items", [])]


# --- an empty store says nothing about anybody ------------------------------
empty = MemorySettings(dict(settings_schema.DEFAULTS))
groups = privacy.inventory(empty)
counted = sum(one["count"] for one in groups)
check("чистая установка ничего о человеке не помнит", counted == 0,
      f"| записей {counted}")

# Group **names** are not in the answer: what a group is called belongs to
# the shell (ADR 0006). Checked, because the easy mistake is to add a
# "title" here and quietly move the decision into the core.
check("группы приходят без названий",
      all("title" not in one for one in groups),
      f"| {[one['id'] for one in groups]}")

# --- what is stored is what is shown ---------------------------------------
s = MemorySettings({
    **settings_schema.DEFAULTS,
    "app_aliases": {"почта": {"path": r"C:\Mail\mail.exe", "name": "Mail"}},
    "history": [
        {"ts": 1700000000.0, "kind": "user", "text": "открой почту",
         "source": "voice"},
    ],
    "todo": [{"id": "t1", "text": "купить хлеб", "done": False}],
    "reminders": [{"id": "r1", "text": "выключить духовку", "when": 1700000900.0}],
    "custom_commands": [
        {"id": "cmd_1", "triggers": ["свернись"], "type": "system",
         "target": "minimize"},
    ],
    "command_stats": {"cmd_1": {"count": 4, "last": 1700000500.0}},
    "enabled_plugins": ["notes"],
    "program_folders": [r"D:\Программы"],
    "wake_word": "Рина-солнце",
})
groups = privacy.inventory(s)

check("выученное слово видно", said(groups, "aliases") == ["почта"],
      f"| {said(groups, 'aliases')}")
check("сказанное человеком видно",
      said(groups, "history") == ["открой почту"],
      f"| {said(groups, 'history')}")
check("дело видно", said(groups, "todo") == ["купить хлеб"],
      f"| {said(groups, 'todo')}")
check("напоминание видно",
      said(groups, "reminders") == ["выключить духовку"],
      f"| {said(groups, 'reminders')}")
check("своя команда видна", said(groups, "commands") == ["свернись"],
      f"| {said(groups, 'commands')}")
check("папка поиска видна", said(groups, "folders") == [r"D:\Программы"],
      f"| {said(groups, 'folders')}")
check("включённый плагин виден", said(groups, "plugins") == ["notes"],
      f"| {said(groups, 'plugins')}")

# Statistics are named by the phrase, not by the identifier: "cmd_1 · 4" is
# a row of a table, and the person is being told about their own habits.
check("статистика названа фразой, а не номером",
      said(groups, "stats") == ["свернись"],
      f"| {said(groups, 'stats')}")

# --- a plugin's own settings are counted, not printed -----------------------
#
# A plugin keeps whatever it likes, an access token included, and this page
# is meant to be read over a shoulder.
s2 = MemorySettings({
    **settings_schema.DEFAULTS,
    "plugin_settings": {"weather": {"api_key": "СЕКРЕТ-1234", "city": "Тверь"}},
})
plugins = group(privacy.inventory(s2), "plugins")
shown = " ".join(f"{i['what']} {i['detail']} {i['where']}"
                 for i in plugins["items"])
check("настройки плагина посчитаны, а не напечатаны",
      "СЕКРЕТ-1234" not in shown and "2" in shown, f"| «{shown}»")

# --- only what was changed, among the preferences ---------------------------
#
# Forty untouched defaults would bury the one setting a person actually
# chose, and a default nobody picked says nothing about anybody.
changed = said(groups, "settings")
check("изменённая настройка попала в опись", "wake_word" in changed,
      f"| {changed}")
check("а нетронутые — нет", "volume" not in changed and len(changed) < 5,
      f"| {changed}")

# --- the load-bearing one: a new store appears by itself --------------------
#
# Not by adding it to a list here — by adding it to the store, the way it
# would actually happen. If this needs upkeep, the page's promise of
# completeness is upkeep too, and upkeep is what fails silently.
was_defaults = dict(settings_schema.DEFAULTS)
try:
    settings_schema.DEFAULTS["mood_journal"] = []
    fresh = MemorySettings({
        **settings_schema.DEFAULTS,
        "mood_journal": [{"note": "устал"}],
    })
    grown = privacy.inventory(fresh)
    check("новый вид хранимого попал в опись сам",
          group(grown, "mood_journal") is not None,
          f"| группы: {[one['id'] for one in grown]}")
    found = group(grown, "mood_journal") or {"count": 0}
    check("и его содержимое видно", found["count"] == 1,
          f"| записей {found['count']}")
finally:
    settings_schema.DEFAULTS.clear()
    settings_schema.DEFAULTS.update(was_defaults)

print()
print("ИТОГО ошибок:", fails)
sys.exit(1 if fails else 0)
