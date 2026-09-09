# -*- coding: utf-8 -*-
"""
4.0b-A07: a plugin declares a tile, and it reaches the home screen.

**The declaring is checked here, the drawing in `--check-home`.** This half
needs no window: what a plugin offers, what the manager keeps of it, and
what goes over the wire are all data, and data is checked without raising an
application.

The rule with teeth is the trimming. A tile that grows becomes a page, and
there is already a place for a page; the limit lives in the core because how
much fits on the home screen is a decision about the home screen, not about
drawing. A shell asking every plugin to behave would be asking politely.
"""
import os
import sys

sys.path.insert(0, r"C:\DevStation\PCDev\DesktopApps\RinaAssistant")
sys.path.insert(0, os.path.join(
    r"C:\DevStation\PCDev\DesktopApps\RinaAssistant", "tools"))

from console import use_utf8
from plugins import manager as manager_mod
from plugins.page_spec import Card, Note, Title

use_utf8()

fails = 0


def check(label, cond, detail=""):
    global fails
    if not cond:
        fails += 1
    print(("OK   " if cond else "FAIL "), label, detail)


class Manifest:
    def __init__(self, name):
        self.id = name
        self.name = name


class Loaded:
    """A plugin as the manager holds it."""

    def __init__(self, name, instance, enabled=True):
        self.manifest = Manifest(name)
        self.instance = instance
        self.enabled = enabled


class Quiet:
    """Offers nothing — which is the right answer for most plugins."""

    def home(self):
        return None


class Talkative:
    """Offers more than fits."""

    def home(self):
        return [Note(f"строка {n}") for n in range(10)]


class Broken:
    """Throws. A plugin is somebody else's code (T-04)."""

    def home(self):
        raise RuntimeError("плагин сломался")


class Weather:
    def home(self):
        return [Card([Title("Мельбурн"), Note("+18°, ясно")],
                     title="Погода")]


def manager_with(*plugins):
    made = manager_mod.PluginManager.__new__(manager_mod.PluginManager)
    made.plugins = {p.manifest.id: p for p in plugins}
    made.log = lambda *a, **k: None
    return made


print("=== кто ничего не просит, того и нет ===")
tiles = manager_with(Loaded("quiet", Quiet())).home_tiles()
check("молчащий плагин плитки не даёт", tiles == [], f"| {tiles}")

print()
print("=== объявленное доезжает ===")
tiles = manager_with(Loaded("weather", Weather())).home_tiles()
check("одна плитка", len(tiles) == 1, f"| {len(tiles)}")
if tiles:
    check("с именем плагина", tiles[0]["title"] == "weather",
          f"| {tiles[0]['title']}")
    check("и с элементами как данными",
          isinstance(tiles[0]["elements"], list)
          and isinstance(tiles[0]["elements"][0], dict),
          f"| {type(tiles[0]['elements'][0]).__name__}")
    # The whole point of ADR 0010 in one assertion: what crosses the wire is
    # a description, not a control.
    check("описание, а не виджет",
          "kind" in tiles[0]["elements"][0],
          f"| {sorted(tiles[0]['elements'][0])[:4]}")

print()
print("=== плитка не разрастается в страницу ===")
tiles = manager_with(Loaded("talkative", Talkative())).home_tiles()
check("лишнее обрезано",
      len(tiles[0]["elements"]) == manager_mod.HOME_TILE_LIMIT,
      f"| {len(tiles[0]['elements'])} при пределе "
      f"{manager_mod.HOME_TILE_LIMIT}")
check("и об этом сказано, а не умолчано", tiles[0]["trimmed"] is True)

print()
print("=== сломавшийся теряет плитку, а не экран ===")
tiles = manager_with(Loaded("broken", Broken()),
                     Loaded("weather", Weather())).home_tiles()
check("упавший пропущен",
      [t["id"] for t in tiles] == ["weather"], f"| {[t['id'] for t in tiles]}")

print()
print("=== выключенный молчит ===")
tiles = manager_with(Loaded("weather", Weather(), enabled=False)).home_tiles()
check("выключенный плагин плитки не даёт", tiles == [], f"| {tiles}")

print()
print("ИТОГО ошибок:", fails)
sys.exit(1 if fails else 0)
