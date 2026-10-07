# -*- coding: utf-8 -*-
"""
A person's plugins live in their profile, the shipped ones beside the program.

Found by the audit of 2026-10-07 (M-7). Plugins were installed into the
program's own `plugins`, and the uninstaller took the program's whole
folder away — the plugins a person installed with it, and everything else
that was in a folder they chose, `D:\\Tools` and all. Installed for all
users under Program Files, the folder was not writable at all.

Checked here, with the program's folder substituted:

- a person's plugin goes to the profile, and one left beside the program
  by an earlier version is moved there — by the build's list of what
  ships, and not at all without one;
- one already in the profile is not overwritten by the older copy;
- a shipped plugin's name cannot be taken: not by installing, not by a
  folder in the profile;
- the core finds both kinds, in or out of a plugin's own process;
- the build writes the list, and the installer keeps to what was decided:
  per user only, never over somebody else's folder, and an uninstall that
  takes only what is its own.

To run:
    python tools/test_plugin_places.py
"""
import io
import json
import os
import re
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

from console import use_utf8
from sandbox import isolate_storage

use_utf8()
isolate_storage()
os.environ.pop("RINA_PLUGINS_DIR", None)

from plugins import manager
from plugins.manager import PluginInstallError, install_plugin

fails = 0


def check(label, cond, detail=""):
    global fails
    if not cond:
        fails += 1
    print(("OK   " if cond else "FAIL "), label, detail)


SOURCE = ("from plugins.api import Plugin\n\n\n"
          "class Probe(Plugin):\n"
          "    def on_command(self, text):\n"
          "        return False\n")


def plugin(base, name):
    folder = os.path.join(base, name)
    os.makedirs(folder, exist_ok=True)
    with io.open(os.path.join(folder, "plugin.json"), "w",
                 encoding="utf-8") as f:
        json.dump({"id": name, "name": name, "api_version": 4}, f)
    with io.open(os.path.join(folder, "main.py"), "w", encoding="utf-8") as f:
        f.write(SOURCE)
    return folder


def shipped_list(names):
    with io.open(os.path.join(program, manager.SHIPPED_LIST), "w",
                 encoding="utf-8") as f:
        json.dump(names, f)


# The program's folder, as an update leaves it: this build's plugin and,
# from before M-7, two a person installed — one of them in the profile too.
program = tempfile.mkdtemp(prefix="rina-program-plugins-")
manager.shipped_dir = lambda: program
plugin(program, "weather")
plugin(program, "mine")
plugin(program, "both")
shipped_list(["weather"])
profile = manager.plugins_dir()
plugin(profile, "both")
with io.open(os.path.join(profile, "both", "newer"), "w") as f:
    f.write("в профиле")

# ---------------------------------------------------------------------------
print("=== где лежат плагины человека ===")
check("в профиле, а не рядом с программой",
      os.path.normcase(profile).startswith(
          os.path.normcase(os.environ["APPDATA"]))
      and os.path.basename(profile) == "plugins", f"| {profile}")

# ---------------------------------------------------------------------------
print()
print("=== перенос после обновления ===")
found = manager.plugin_folders()
check("плагин человека переехал в профиль",
      os.path.isfile(os.path.join(profile, "mine", "plugin.json"))
      and not os.path.exists(os.path.join(program, "mine")))
check("и найден там", found.get("mine") == os.path.join(profile, "mine"),
      f"| {found.get('mine')}")
check("плагин поставки остался на месте",
      found.get("weather") == os.path.join(program, "weather"))
check("копия, что уже в профиле, не перезаписана старой",
      os.path.isfile(os.path.join(profile, "both", "newer"))
      and found.get("both") == os.path.join(profile, "both"))
check("повторный поиск ничего не двигает", manager.move_user_plugins() == [])

# ---------------------------------------------------------------------------
print()
print("=== имя плагина поставки занять нельзя ===")
plugin(profile, "weather")
check("папка в профиле с именем поставки не подменяет её",
      manager.plugin_folders()["weather"] == os.path.join(program, "weather"))
shutil.rmtree(os.path.join(profile, "weather"))

with tempfile.TemporaryDirectory() as staging:
    for name in ("weather", "Weather"):
        source = plugin(staging, name)
        try:
            install_plugin(source)
            refused = ""
        except PluginInstallError as e:
            refused = str(e)
        check(f"установка под именем «{name}» отклонена с причиной",
              "поставки" in refused, f"| {refused or 'установлен'}")
        shutil.rmtree(source)
    source = plugin(staging, "fresh")
    plugin_id, replaced = install_plugin(source)
    check("обычный плагин ставится в профиль",
          os.path.isfile(os.path.join(profile, "fresh", "plugin.json"))
          and not os.path.exists(os.path.join(program, "fresh")))

# ---------------------------------------------------------------------------
print()
print("=== без списка сборки — ничего не трогаем ===")
os.remove(os.path.join(program, manager.SHIPPED_LIST))
plugin(program, "unknown")
check("из исходников всё рядом с программой — поставка",
      "unknown" in manager.shipped_ids() and manager.move_user_plugins() == []
      and os.path.isdir(os.path.join(program, "unknown")))
shutil.rmtree(os.path.join(program, "unknown"))
shipped_list(["weather"])

# ---------------------------------------------------------------------------
print()
print("=== ядро видит оба вида ===")
from core.plugin_host import HostedPlugins
from core.settings_api import MemorySettings

hosted = HostedPlugins(MemorySettings({}))
hosted.discover()
check("в процессах плагинов — из поставки и из профиля",
      {"weather", "mine", "both", "fresh"} <= set(hosted.plugins)
      and hosted.plugins["mine"].folder == os.path.join(profile, "mine"),
      f"| {sorted(hosted.plugins)}")
ran = hosted.enable("mine", persist=False)
check("плагин из профиля запускается в своём процессе",
      ran and not hosted.plugins["mine"].error,
      f"| {hosted.plugins['mine'].error}")
for one in hosted.plugins.values():
    one.stop()

# ---------------------------------------------------------------------------
print()
print("=== сборка называет плагины поставки ===")
import build_release

built = tempfile.mkdtemp(prefix="rina-built-plugins-")
plugin(built, "rates")
plugin(built, "weather")
os.makedirs(os.path.join(built, "__pycache__"))
build_release.write_shipped_list(built)
with io.open(os.path.join(built, "shipped.json"), encoding="utf-8") as f:
    check("shipped.json — ровно папки плагинов",
          json.load(f) == ["rates", "weather"])

# ---------------------------------------------------------------------------
print()
print("=== установщик ===")
with io.open(os.path.join(ROOT, "packaging", "rina.iss"),
             encoding="utf-8-sig") as f:
    script = f.read()
lines = [line.split(";", 1)[0].strip() for line in script.splitlines()]
check("только в профиль: выбора «для всех» нет",
      "PrivilegesRequired=lowest" in lines
      and not any(l.startswith("PrivilegesRequiredOverridesAllowed")
                  for l in lines))
check("обновление — в прежнюю папку", "UsePreviousAppDir=yes" in lines)
check("в непустую чужую папку не ставит — и в тихой установке тоже",
      "function PrepareToInstall" in script
      and "IsForeignFolder(ExpandConstant('{app}'))" in script)
removed = re.findall(r'^Type:\s*(\w+);\s*Name:\s*"([^"]+)"', script, re.M)
check("удаление не забирает папку целиком",
      ("filesandordirs", "{app}") not in removed
      and ("dirifempty", "{app}") in removed, f"| {removed}")
check("и плагины человека при удалении уходят в профиль, а не в корзину",
      "KeepPersonsPlugins" in script and "usUninstall" in script
      and r"{userappdata}\RinaAssistant\plugins" in script)

shutil.rmtree(program, ignore_errors=True)
shutil.rmtree(built, ignore_errors=True)

print()
print("ИТОГО ошибок:", fails)
sys.exit(1 if fails else 0)
