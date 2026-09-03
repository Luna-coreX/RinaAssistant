# -*- coding: utf-8 -*-
"""
Блок H: плагин объявляет, а не делает.

Проверяется то, что должно случиться, и наравне с ним — то, чего случиться
не должно: инструмент без разрешения не заводится, старый плагин не
загружается молча, выключенный не оставляет за собой инструментов.

Запуск:
    python tools/test_plugins.py
"""
import io
import json
import os
import shutil
import sys
import time

ROOT = r"C:\DevStation\PCDev\DesktopApps\RinaAssistant"
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
os.chdir(ROOT)

from console import use_utf8
from sandbox import isolate_storage, neutralise

# Кубик отвечает эмодзи, а на консоли с кодовой страницей Windows это
# `UnicodeEncodeError` прямо в подписи результата. Проверка, зелёная под
# одним запуском и красная под другим, хуже отсутствующей.
use_utf8()

isolate_storage()
box = neutralise()

from core.engine import RinaEngine
from core.events import EventBus
from core.permissions import PERMISSIONS, PLUGIN_FORBIDDEN, plugin_allowed
from plugins.api import API_VERSION, MIN_API_VERSION, PluginManifest
from plugins.manager import PluginManager, plugins_dir
from plugins.page_spec import (CONTAINERS, KINDS, MAX_DEPTH, SCHEMA_VERSION,
                               Card, Group, Note, Row, Title, page_to_dict)

fails = 0


def check(label, cond, detail=""):
    global fails
    if not cond:
        fails += 1
    print(("OK   " if cond else "FAIL "), label, detail)


# ---------------------------------------------------------------------------
print("=== H01: схема выражает страницу в новом дизайне ===")

check("схема второй версии", SCHEMA_VERSION == 2)
check("контейнеры появились",
      set(CONTAINERS) == {"card", "group", "row"}, f"| {CONTAINERS}")
check("словарь версии 1 целиком внутри версии 2",
      {"title", "text", "note", "items", "button", "input", "table",
       "progress", "badge", "divider"}.issubset(set(KINDS)),
      "| иначе переезд плагина стоил бы правок")

page = page_to_dict([
    Card([Title("Заголовок"), Note("Подпись")], title="Карточка"),
    Group([Row([Note("а"), Note("б")])], title="Секция"),
])
check("карточка несёт содержимое",
      page[0]["kind"] == "card" and len(page[0]["children"]) == 2,
      f"| {page[0]}")
check("вложенность сериализуется целиком",
      page[1]["children"][0]["children"][0]["text"] == "а",
      f"| {page[1]}")
check("пустой контейнер не несёт детей",
      "children" not in page_to_dict([Card([])])[0],
      "| рамка вокруг ничего выглядит как поломка")
check("чужое в детях не проходит",
      page_to_dict([Card(["строка", None, Note("настоящий")])])[0]
      ["children"] == [{"kind": "note", "text": "настоящий"}])

# Ни одного поля о внешности — правило с зубами из PAGE-SCHEMA-v2: плагин
# говорит «предупреждение», а не «оранжевый». Смотрим на поля элемента, а
# не на текст файла: в тексте эти слова как раз и стоят — в объяснении,
# почему их здесь нет.
from plugins.page_spec import Element

looks = [name for name in Element.__dataclass_fields__
         if name in ("color", "background", "padding", "margin", "font",
                     "width", "height", "size", "style", "align")]
check("в схеме нет полей о внешности", not looks, f"| {looks}")
check("глубина ограничена", MAX_DEPTH > 0 and MAX_DEPTH <= 8,
      f"| {MAX_DEPTH}")

# Рендерер обязан знать все виды словаря: список сверяется с C#.
#
# Смотрим в `PluginView`: рендерер вынут туда, когда у плагина появился
# свой раздел в колонке. Один на обе стороны — два рендерера одной схемы
# разъехались бы на первой правке, и эта проверка ровно на переезд и
# сработала.
renderer = io.open("shell/Rina.Shell/Pages/PluginView.xaml.cs",
                   encoding="utf-8").read()
unknown = [kind for kind in KINDS if f'case "{kind}"' not in renderer]
check("рендерер знает каждый вид словаря", not unknown, f"| {unknown}")
check("и глубина у него та же",
      f"MaxDepth = {MAX_DEPTH}" in renderer,
      "| два разных предела значат, что один из них не работает")


# ---------------------------------------------------------------------------
print()
print("=== H03: плагин объявляет инструменты ===")

manager = PluginManager()
manager.discover()
check("плагины найдены", len(manager.plugins) >= 4,
      f"| {sorted(manager.plugins)}")

engine = RinaEngine(plugin_manager=manager, event_bus=EventBus())


def plugin_tools():
    return [n for n in engine._tools.registry.names()
            if n.startswith("plugin.")]


check("до включения инструментов нет", not plugin_tools())

manager.enable("dice")
check("включение завело инструменты",
      "plugin.dice.roll" in plugin_tools(), f"| {plugin_tools()}")
check("имя с префиксом плагина",
      all(n.startswith("plugin.dice.") for n in plugin_tools()),
      "| два плагина с инструментом roll иначе спорили бы за одно имя")

result = engine._tools.call("plugin.dice.roll", {"sides": 20})
check("инструмент плагина вызывается через реестр", result.ok,
      f"| {result.message}")

refused = engine._tools.call("plugin.dice.roll", {"sides": 500})
check("аргументы проверяет реестр, а не плагин",
      not refused.ok and refused.error_code == "tool.invalid_arguments",
      f"| {refused.error_code}")

check("вызов записан в журнал",
      any("plugin.dice.roll" in str(row) for row in engine._tools.audit.recent(5)),
      "| по журналу должно быть видно, какой плагин это затеял")

manager.disable("dice")
check("выключение сняло инструменты", not plugin_tools(), f"| {plugin_tools()}")
gone = engine._tools.call("plugin.dice.roll", {})
check("снятый инструмент неизвестен реестру",
      not gone.ok and gone.error_code == "tool.unknown", f"| {gone.error_code}")


# ---------------------------------------------------------------------------
print()
print("=== H06: границы плагина ===")

check("каталог разрешений один", all(name in PERMISSIONS
                                     for name in PLUGIN_FORBIDDEN),
      "| второй каталог «для плагинов» разошёлся бы с первым")
check("выключение компьютера плагину не выдаётся",
      "system.power" in PLUGIN_FORBIDDEN)
check("запись файлов плагину не выдаётся",
      "files.write" in PLUGIN_FORBIDDEN)
check("зарезервированное под 5.0 не выдаётся",
      {"screen.read", "input.synthesize"} <= PLUGIN_FORBIDDEN)

ok, no = plugin_allowed(["process.launch", "system.power", "выдумка"])
check("разрешённое пропускается", ok == ["process.launch"], f"| {ok}")
check("запрещённое и незнакомое отклоняется",
      no == ["system.power", "выдумка"], f"| {no}")

check("ни один встроенный плагин не просит запрещённого",
      all(not (set(lp.manifest.permissions) & PLUGIN_FORBIDDEN)
          for lp in manager.plugins.values()),
      "| иначе пример учил бы просить то, чего не дают")


# ---------------------------------------------------------------------------
print()
print("=== H05: старый плагин не загружается молча ===")

check("минимальная версия API объявлена",
      MIN_API_VERSION == API_VERSION == 4,
      f"| {MIN_API_VERSION}..{API_VERSION}")

old = PluginManifest(id="ветхий", name="Ветхий", api_version=2)
check("плагин версии 2 несовместим", not old.api_compatible())
why = old.why_incompatible()
check("причина названа словами", "page()" in why and "create_page" in why,
      f"| {why}")
check("и сказано, что делать", "Обновите" in why, f"| {why}")

future = PluginManifest(id="будущий", name="Будущий", api_version=99)
check("плагин из будущего тоже отклонён", not future.api_compatible())
check("но с другой причиной",
      "Обновите Рину" in future.why_incompatible(),
      f"| {future.why_incompatible()}")

check("create_page больше нет в API",
      "def create_page" not in io.open("plugins/api.py", encoding="utf-8").read(),
      "| виджет привязывал ядро к оболочке — это был блокер разделения")
check("и открыть своё окно плагин не может",
      "def open_window" not in io.open("plugins/api.py",
                                       encoding="utf-8").read())

# Настоящий старый плагин на диске: проверка обнаружения, а не только
# разбора манифеста.
sample = os.path.join(plugins_dir(), "проверка_ветхого")
try:
    os.makedirs(sample, exist_ok=True)
    io.open(os.path.join(sample, "plugin.json"), "w",
            encoding="utf-8").write(json.dumps(
                {"id": "ветхий", "name": "Ветхий", "api_version": 1},
                ensure_ascii=False))
    io.open(os.path.join(sample, "main.py"), "w", encoding="utf-8").write(
        "from plugins.api import Plugin\n\n\n"
        "class Old(Plugin):\n    pass\n")

    second = PluginManager()
    second.discover()
    found = second.plugins.get("проверка_ветхого")
    check("старый плагин виден в списке", found is not None)
    check("и помечен сбойным с причиной",
          bool(found and found.error and "page()" in found.error),
          f"| {found.error if found else ''}")
    check("включить его нельзя",
          not (second.enable("проверка_ветхого")
               and second.plugins["проверка_ветхого"].enabled))
finally:
    shutil.rmtree(sample, ignore_errors=True)


# ---------------------------------------------------------------------------
print()
print("=== H04: встроенные плагины переехали ===")

for plugin_id in ("clock", "dice", "greeter", "notes"):
    loaded = manager.plugins.get(plugin_id)
    check(f"«{plugin_id}» на четвёртой версии",
          bool(loaded) and loaded.manifest.api_version == 4,
          f"| {loaded.manifest.api_version if loaded else '—'}")

manager.enable("notes")
elements = manager.get_plugin_page_spec("notes")
check("страница заметок описана", bool(elements))
check("и пользуется контейнерами",
      any(e.kind in CONTAINERS for e in elements),
      f"| {[e.kind for e in elements]}")

drawn = page_to_dict(elements)
check("страница сериализуется без потерь",
      json.loads(json.dumps(drawn, ensure_ascii=False)) == drawn)

# Действие возвращает новую страницу целиком — частичных обновлений нет.
manager.dispatch_action("notes", "add", "проверка")
after = page_to_dict(manager.get_plugin_page_spec("notes"))
check("действие изменило страницу", after != drawn)
manager.dispatch_action("notes", "clear")

check("ни один плагин не импортирует интерфейсную библиотеку",
      not [pid for pid in manager.plugins
           if "PySide6" in io.open(
               os.path.join(plugins_dir(), pid, "main.py"),
               encoding="utf-8").read()],
      "| это и был прямой блокер разделения процессов")

# ---------------------------------------------------------------------------
print()
print("=== H07: плагин в отдельном процессе ===")

from core.plugin_host import HostedPlugins
from core.settings_store import SettingsStore

store = SettingsStore()
store.load()
hosted = HostedPlugins(settings=store)
hosted.discover()
check("плагины видны до запуска", len(hosted.plugins) >= 4,
      "| список плагинов не должен стоить столько же, сколько их запуск")
# Поднимается ровно то, что человек включал: обнаружение восстанавливает
# состояние, а не запускает всё подряд.
was_enabled = set(store.get("enabled_plugins", []) or [])
check("подняты только те, что были включены",
      {pid for pid, h in hosted.plugins.items() if h.alive} <= was_enabled,
      f"| включены {sorted(was_enabled)}")

check("включение поднимает процесс", hosted.enable("dice"))
dice = hosted.plugins["dice"]
check("процесс жив", dice.alive)
check("плагин представился",
      dice.manifest.api_version == 4 and dice.manifest.name != "dice",
      f"| {dice.manifest.name} api={dice.manifest.api_version}")

remote = dict((t.name, r) for t, r in hosted.declared_tools("dice"))
check("инструменты доехали по проводу",
      "plugin.dice.roll" in remote, f"| {sorted(remote)}")
answer = remote["plugin.dice.roll"](None, {"sides": 6})
check("инструмент выполняется в чужом процессе", answer.ok,
      f"| {answer.message}")

hosted.enable("notes")
spoken = []
hosted.response.connect(lambda pid, text: spoken.append((pid, text)))
check("команда доходит до плагина",
      hosted.dispatch_command("запиши молоко"))
check("и его реплика возвращается ядру",
      any("молоко" in text for _, text in spoken), f"| {spoken}")

page = hosted.get_plugin_page_spec("notes")
check("страница приходит по проводу", bool(page),
      f"| {[e.kind for e in page]}")
check("и это карточка, а не столбик абзацев",
      any(e.kind in CONTAINERS for e in page))

# Настройки плагина хранит ядро: они переживают падение самого плагина.
check("своя настройка плагина записана ядром",
      bool(store.get("plugin_settings", {}).get("notes", {}).get("items")),
      f"| {store.get('plugin_settings')}")
hosted.dispatch_action("notes", "clear")


# --- зависший -------------------------------------------------------------
sample = os.path.join(plugins_dir(), "проверка_зависшего")
crashing = os.path.join(plugins_dir(), "проверка_падшего")
try:
    os.makedirs(sample, exist_ok=True)
    io.open(os.path.join(sample, "plugin.json"), "w",
            encoding="utf-8").write(json.dumps(
                {"id": "зависший", "name": "Зависший", "api_version": 4},
                ensure_ascii=False))
    io.open(os.path.join(sample, "main.py"), "w", encoding="utf-8").write(
        "import time\n"
        "from plugins.api import Plugin\n\n\n"
        "class Frozen(Plugin):\n"
        "    def on_command(self, text):\n"
        "        while True:\n"
        "            time.sleep(1)\n")

    os.makedirs(crashing, exist_ok=True)
    io.open(os.path.join(crashing, "plugin.json"), "w",
            encoding="utf-8").write(json.dumps(
                {"id": "падший", "name": "Падший", "api_version": 4},
                ensure_ascii=False))
    io.open(os.path.join(crashing, "main.py"), "w", encoding="utf-8").write(
        "import os\n"
        "from plugins.api import Plugin\n\n\n"
        "class Crasher(Plugin):\n"
        "    def on_command(self, text):\n"
        "        os._exit(3)\n")

    third = HostedPlugins(settings=store)
    third.discover()
    check("зависший и падший найдены",
          "проверка_зависшего" in third.plugins
          and "проверка_падшего" in third.plugins)

    third.enable("проверка_зависшего")
    third.enable("проверка_падшего")
    third.enable("clock")

    frozen = third.plugins["проверка_зависшего"]
    started = time.monotonic()
    reply = frozen.ask("plugin.command", {"text": "повисни"}, timeout=2.0)
    spent = time.monotonic() - started

    check("зависший не отвечает", reply is None)
    check("и ожидание кончается по сроку", spent < 6.0, f"| {spent:.1f} с")
    check("процесс остановлен", not frozen.alive,
          "| процесс, который не отвечает, занимает память и ничего не даёт")
    check("и он помечен сбойным с причиной",
          bool(frozen.error) and "не ответил" in frozen.error,
          f"| {frozen.error}")
    check("выключен, а не оставлен включённым", not frozen.enabled)

    crash = third.plugins["проверка_падшего"]
    crash.ask("plugin.command", {"text": "упади"}, timeout=3.0)
    for _ in range(30):
        if not crash.alive:
            break
        time.sleep(0.1)
    check("падший упал", not crash.alive)

    # И главное: ассистент после этого работает.
    check("соседний плагин цел",
          third.plugins["clock"].alive and third.plugins["clock"].enabled)
    check("ядро продолжает разбирать команды",
          third.dispatch_command("который час"),
          "| это и есть критерий приёмки H07")

    engine2 = RinaEngine(plugin_manager=third, event_bus=EventBus())
    said2 = []
    engine2.say = lambda text, sound="response": said2.append(text)
    engine2.handle_command("посчитай 2+2")
    check("и ассистент отвечает как обычно",
          any("4" in text for text in said2), f"| {said2}")

    third.stop_all()
finally:
    shutil.rmtree(sample, ignore_errors=True)
    shutil.rmtree(crashing, ignore_errors=True)

hosted.stop_all()
check("после остановки не осталось процессов",
      not any(h.alive for h in hosted.plugins.values()))

check("поверхность совпадает с менеджером в процессе",
      not [name for name in ("discover", "enable", "disable", "toggle",
                             "dispatch_command", "broadcast_event",
                             "page_plugins", "get_plugin_page_spec",
                             "dispatch_action", "declared_tools",
                             "tool_prefix", "get_plugin_setting",
                             "set_plugin_setting")
           if not (hasattr(HostedPlugins, name)
                   and hasattr(PluginManager, name))],
      "| ядро не должно знать, где живёт плагин")


print()
print("ИТОГО ошибок:", fails)
sys.exit(1 if fails else 0)
