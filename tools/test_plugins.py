# -*- coding: utf-8 -*-
"""
Block H: a plugin declares rather than does.

What must happen is checked, and on a par with it what must not: a tool
without a permission is not created, an old plugin does not load in silence,
a switched-off one leaves no tools behind.

To run:
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
from sandbox import isolate_plugins, isolate_storage, neutralise

# The die answers with an emoji, and on a console with a Windows code page
# that is a `UnicodeEncodeError` right inside the result's caption. A check
# that is green under one run and red under another is worse than none.
use_utf8()

isolate_storage()
# The examples are not in `plugins/` since `4.0b-K05`; this puts them next
# to the shipped plugins, in a folder of the check's own.
isolate_plugins()
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

# Not one field about appearance — the rule with teeth from PAGE-SCHEMA-v2: a
# plugin says "warning", not "orange". We look at an element's fields rather
# than at the file's text: in the text those very words do appear — in the
# explanation of why they are not here.
from plugins.page_spec import Element

looks = [name for name in Element.__dataclass_fields__
         if name in ("color", "background", "padding", "margin", "font",
                     "width", "height", "size", "style", "align")]
check("в схеме нет полей о внешности", not looks, f"| {looks}")
check("глубина ограничена", MAX_DEPTH > 0 and MAX_DEPTH <= 8,
      f"| {MAX_DEPTH}")

# The renderer is obliged to know every kind in the dictionary: the list is
# compared with the C# one.
#
# We look into `PluginView`: the renderer was moved there when a plugin got a
# section of its own in the column. One for both sides — two renderers of one
# schema would part company at the first change, and this check fired on
# precisely that move.
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

# 4.0-H10: a plugin's tool is a block of a person's own command. Through
# the same registry, so the same gates — and the same journal.
blocks = {t.name: t for t in engine._tools.blocks()}
check("инструмент плагина стал блоком конструктора",
      "plugin.dice.roll" in blocks, f"| {sorted(blocks)}")
check("плагин сказал, что кубик только отвечает",
      blocks.get("plugin.dice.roll") and
      blocks["plugin.dice.roll"].automation == "query")
check("и поле блока — аргумент плагина",
      blocks.get("plugin.dice.roll") and
      blocks["plugin.dice.roll"].asks == ("sides",))

from voice.user_commands import execute

heard = []
ok, _said = execute(
    {"type": "sequence", "steps": [
        {"type": "get", "tool": "plugin.dice.roll", "args": {"sides": 6},
         "name": "кубик"},
        {"type": "speak", "target": "Кубик: {кубик}"}]},
    say=heard.append, call_block=engine._tools.call_block,
    block_effect=engine._tools.block_effect)
check("своя команда вызывает инструмент плагина",
      ok and heard and heard[0].startswith("Кубик: ")
      and "{кубик}" not in heard[0], f"| {heard}")
from_command = [r for r in engine._tools.audit.recent(5)
                if r["tool"] == "plugin.dice.roll"]
check("и вызов в журнале — от команды",
      from_command and from_command[0]["source"] == "command",
      f"| {[(r['tool'], r['source']) for r in from_command]}")

manager.disable("dice")
check("выключение сняло инструменты", not plugin_tools(), f"| {plugin_tools()}")
gone = engine._tools.call("plugin.dice.roll", {})
check("снятый инструмент неизвестен реестру",
      not gone.ok and gone.error_code == "tool.unknown", f"| {gone.error_code}")
check("и блоком больше не предлагается",
      "plugin.dice.roll" not in {t.name for t in engine._tools.blocks()})
left = engine._tools.call_block("plugin.dice.roll", {"sides": 6})
check("команда с блоком выключенного плагина получает отказ, а не сбой",
      not left.ok and left.error_code == "tool.unknown",
      f"| {left.error_code}")


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

# A real old plugin on disk: a check of discovery, not only of parsing the
# manifest.
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

# An action returns a whole new page — there are no partial updates.
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
# Exactly what a person switched on comes up: discovery restores the state
# rather than starting everything in sight.
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

# A parameter's default crosses the wire. The core rebuilds each `Param`
# from the description the plugin sent at the introduction, and it used to
# leave `default` behind: the registry then had nothing to substitute, and
# an optional argument simply did not arrive at `run`.
from core.tools import validate

defaulted = os.path.join(plugins_dir(), "проверка_умолчания")
try:
    os.makedirs(defaulted, exist_ok=True)
    io.open(os.path.join(defaulted, "plugin.json"), "w",
            encoding="utf-8").write(json.dumps(
                {"id": "умолчание", "name": "Умолчание", "api_version": 4},
                ensure_ascii=False))
    io.open(os.path.join(defaulted, "main.py"), "w", encoding="utf-8").write(
        "from core.tools import Param\n"
        "from plugins.api import Plugin, PluginTool\n\n\n"
        "class Defaulted(Plugin):\n"
        "    def tools(self):\n"
        "        return [PluginTool(\n"
        "            name='count', summary='Назвать число.',\n"
        "            params=(Param('n', 'integer', 'Число.', required=False,\n"
        "                          default=7),),\n"
        "            run=lambda args: str(args.get('n')))]\n")
    hosted.discover()
    check("плагин с умолчанием поднят", hosted.enable("проверка_умолчания"),
          f"| {hosted.plugins.get('проверка_умолчания') and hosted.plugins['проверка_умолчания'].error}")
    made = dict((t.name, (t, r)) for t, r in hosted.declared_tools("проверка_умолчания"))
    tool, run = made.get("plugin.проверка_умолчания.count", (None, None))
    check("умолчание параметра доехало до ядра",
          tool is not None and tool.param("n").default == 7,
          f"| {tool and tool.param('n')}")
    if tool is not None:
        filled = validate(tool, {})
        check("реестр подставляет его, если аргумент не пришёл",
              filled == {"n": 7}, f"| {filled}")
        said = run(None, filled)
        check("и плагин получает его в run", said.ok and said.message == "7",
              f"| {said.message!r}")
finally:
    hosted.disable("проверка_умолчания", persist=False)
    shutil.rmtree(defaulted, ignore_errors=True)
    hosted.discover()

# A refusal worded by the plugin crosses the process boundary as words
# (`4.0b-K06`): the person hears «Город не задан», not «the plugin did not
# answer», and the plugin's log gets no traceback for a plain "no".
refusing = os.path.join(plugins_dir(), "проверка_отказа")
try:
    os.makedirs(refusing, exist_ok=True)
    io.open(os.path.join(refusing, "plugin.json"), "w",
            encoding="utf-8").write(json.dumps(
                {"id": "отказ", "name": "Отказ", "api_version": 4},
                ensure_ascii=False))
    io.open(os.path.join(refusing, "main.py"), "w", encoding="utf-8").write(
        "from plugins.api import Plugin, PluginTool, ToolFailed\n\n\n"
        "def no(args):\n"
        "    raise ToolFailed('Город не задан.')\n\n\n"
        "class Refusing(Plugin):\n"
        "    def tools(self):\n"
        "        return [PluginTool(name='ask', summary='Спросить.',\n"
        "                           reads=True, run=no)]\n")
    hosted.discover()
    check("плагин с отказом поднят", hosted.enable("проверка_отказа"))
    made = dict((t.name, r) for t, r in hosted.declared_tools("проверка_отказа"))
    run = made.get("plugin.проверка_отказа.ask")
    refused = run(None, {}) if run else None
    check("отказ плагина доходит словами, а не «плагин не ответил»",
          refused is not None and not refused.ok
          and refused.message == "Город не задан.",
          f"| {refused and refused.message!r}")
    check("и процесс плагина от него не падает",
          hosted.plugins["проверка_отказа"].alive)
finally:
    hosted.disable("проверка_отказа", persist=False)
    shutil.rmtree(refusing, ignore_errors=True)
    hosted.discover()

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

# A plugin's settings are kept by the core: they outlive the plugin's own crash.
check("своя настройка плагина записана ядром",
      bool(store.get("plugin_settings", {}).get("notes", {}).get("items")),
      f"| {store.get('plugin_settings')}")
hosted.dispatch_action("notes", "clear")


# --- the hung one ---------------------------------------------------------
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

    # And the main thing: the assistant works afterwards.
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

# --- the greedy one and the chatty one -----------------------------------
#
# A plugin that announces a frame of four gigabytes. The decoder refuses
# such a length before allocating; the host used to read the whole body
# first and hand it over afterwards, which undid the refusal. What is asked
# is that the length is judged at once — the plugin is stopped with its
# reason, not left to time out, and not read.
#
# And one that prints a lot. `plugins/host.py` sends `print` to the error
# stream, which nobody read: after a few kilobytes the plugin hung inside
# `print`, and from here that looked like a plugin that stopped answering.
greedy = os.path.join(plugins_dir(), "проверка_жадного")
chatty = os.path.join(plugins_dir(), "проверка_болтливого")
try:
    for folder, pid, body in (
            (greedy, "жадный",
             "import sys, time\n"
             "from plugins.api import Plugin\n\n\n"
             "class Greedy(Plugin):\n"
             "    def on_command(self, text):\n"
             "        sys.__stdout__.buffer.write(b'\\xff\\xff\\xff\\xf0' + b'x' * 16)\n"
             "        sys.__stdout__.buffer.flush()\n"
             "        time.sleep(30)\n"),
            (chatty, "болтливый",
             "from plugins.api import Plugin\n\n\n"
             "class Chatty(Plugin):\n"
             "    def on_command(self, text):\n"
             "        for i in range(20000):\n"
             "            print('строка отладки номер', i)\n"
             "        return True\n")):
        os.makedirs(folder, exist_ok=True)
        io.open(os.path.join(folder, "plugin.json"), "w",
                encoding="utf-8").write(json.dumps(
                    {"id": pid, "name": pid.title(), "api_version": 4},
                    ensure_ascii=False))
        io.open(os.path.join(folder, "main.py"), "w",
                encoding="utf-8").write(body)

    fourth = HostedPlugins(settings=store)
    fourth.discover()
    fourth.enable("проверка_жадного")
    fourth.enable("проверка_болтливого")
    fourth.enable("clock")

    hungry = fourth.plugins["проверка_жадного"]
    started = time.monotonic()
    reply = hungry.ask("plugin.command", {"text": "съешь память"}, timeout=8.0)
    spent = time.monotonic() - started
    check("кадр сверх предела останавливает плагин сразу, а не по сроку",
          reply is None and spent < 4.0 and not hungry.alive,
          f"| {spent:.1f} с, жив: {hungry.alive}")
    check("и причина названа", "слишком большое" in (hungry.error or ""),
          f"| {hungry.error}")

    talker = fourth.plugins["проверка_болтливого"]
    reply = talker.ask("plugin.command", {"text": "болтай"}, timeout=8.0)
    check("болтливый плагин отвечает, а не виснет в print",
          reply is not None and reply.get("handled") is True,
          f"| {reply} {talker.error}")
    check("и хвост его вывода виден в его журнале",
          any("строка отладки" in line for line in talker.logs),
          f"| {talker.logs[-2:]}")
    check("соседний плагин цел и после них",
          fourth.plugins["clock"].alive)
    fourth.stop_all()
finally:
    shutil.rmtree(greedy, ignore_errors=True)
    shutil.rmtree(chatty, ignore_errors=True)

hosted.stop_all()
check("после остановки не осталось процессов",
      not any(h.alive for h in hosted.plugins.values()))

print()
print("=== H07: плитка приезжает из чужого процесса ===")
# The surface check above says the method is there; this one says it works.
# Both are needed, and for the same reason: `home_tiles` existed all along
# — on the class that does not run.
#
# A plugin written here rather than one of ours: the only shipped plugin
# with a tile wants a city in its settings and the network, and a check
# that needs the weather is a check that goes red on a train.
import json
import tempfile

from core.plugin_host import HostedPlugin
from plugins.manager import HOME_TILE_LIMIT

probe = os.path.join(tempfile.mkdtemp(prefix="rina-tile-"), "tileprobe")
os.makedirs(probe)
io.open(os.path.join(probe, "plugin.json"), "w", encoding="utf-8").write(
    json.dumps({"id": "tileprobe", "name": "Плитка", "version": "1.0.0",
                "author": "проверка", "description": "плитка для проверки",
                "icon": "🧪", "entry": "TileProbe", "api_version": 4},
               ensure_ascii=False))
io.open(os.path.join(probe, "main.py"), "w", encoding="utf-8").write(
    "from plugins.api import Plugin\n"
    "from plugins.page_spec import Note\n"
    "\n"
    "\n"
    "class TileProbe(Plugin):\n"
    "    def home(self):\n"
    "        return [Note(f'строка {n}') for n in range(10)]\n")

tile_host = HostedPlugins(settings=store)
# The real plugins too, so that "the one without a tile does not appear"
# has somebody to be true about. Without this the list held our probe
# alone, and the assertion passed by having nothing to exclude.
tile_host.discover()
alone = HostedPlugin(probe, tile_host)
tile_host.plugins["tileprobe"] = alone
check("плагин с плиткой поднялся", alone.start(), f"| {alone.error}")
alone.enabled = True
check("и сказал при знакомстве, что плитка у него есть", alone.has_home,
      "| иначе ядро не станет и спрашивать")

tiles = tile_host.home_tiles()
check("плитка доехала через провод", len(tiles) == 1, f"| {len(tiles)}")
if tiles:
    check("с именем плагина", tiles[0]["title"] == "Плитка",
          f"| {tiles[0]['title']}")
    check("элементы — описания, а не виджеты",
          isinstance(tiles[0]["elements"][0], dict)
          and "kind" in tiles[0]["elements"][0],
          f"| {sorted(tiles[0]['elements'][0])[:4]}")
    check("лишнее обрезано и об этом сказано",
          len(tiles[0]["elements"]) == HOME_TILE_LIMIT
          and tiles[0]["trimmed"] is True,
          f"| {len(tiles[0]['elements'])} при пределе "
          f"{HOME_TILE_LIMIT}")

# And the one that wants nothing is not asked at all: `dice` has no `home`,
# so it must not appear even while it is running.
check("сосед без плитки тоже запущен", tile_host.enable("dice"),
      "| иначе исключать некого")
check("плагин без плитки в списке не появляется",
      [t["id"] for t in tile_host.home_tiles()] == ["tileprobe"],
      f"| {[t['id'] for t in tile_host.home_tiles()]}")
tile_host.stop_all()
alone.kill()

print()
# The surface, read out of the core rather than listed here.
#
# **The list used to be written out by hand, and that is how the home
# screen lost its tiles.** `home_tiles` was added to `PluginManager` for
# `4.0b-A07`, plugins live in processes of their own (ADR 0010), and the
# core talks to `HostedPlugins` — which never grew the method. The core
# logged `'HostedPlugins' object has no attribute 'home_tiles'` every few
# seconds for four days while this check stayed green, because the name
# was not in the list and nobody thought to put it there. A list kept by
# hand records what somebody remembered, and the thing worth checking is
# exactly what they forgot.
#
# So the names are taken from the core's own text: whatever it calls on
# its manager has to exist on both. `plugins.get(...)` and friends are not
# collected — that is the dictionary, not the manager.
import re

asked = set()
for folder, _dirs, files in os.walk(
        os.path.join(r"C:\DevStation\PCDev\DesktopApps\RinaAssistant", "core")):
    if "__pycache__" in folder:
        continue
    for name in files:
        if not name.endswith(".py"):
            continue
        text = io.open(os.path.join(folder, name), encoding="utf-8").read()
        asked |= set(re.findall(r"(?:manager|self\._plugins)\.([a-z_]+)\(",
                                text))

check("ядро вообще что-то просит у менеджера", len(asked) >= 5,
      f"| {sorted(asked)}")
missing = sorted(name for name in asked
                 if not (hasattr(HostedPlugins, name)
                         and hasattr(PluginManager, name)))
check("всё, что ядро просит, есть у обоих менеджеров", not missing,
      f"| нет у одного из них: {missing}" if missing
      else f"| проверено имён: {len(asked)}")


# ---------------------------------------------------------------------------
# «Курс» asks the Central Bank and nobody else
# ---------------------------------------------------------------------------
#
# It used to ask a third-party mirror first while the product page said "a
# request to the central bank's website". Decided 2026-09-29: the bank
# only, and yesterday's value — the arrow — from the bank as well.
print()
print("=== «Курс»: только Центробанк ===")
import importlib.util
import urllib.request

spec = importlib.util.spec_from_file_location(
    "rates_main", os.path.join(plugins_dir(), "rates", "main.py"))
rates = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rates)


def bank_page(day, usd, eur):
    return (f'<?xml version="1.0" encoding="windows-1251"?>'
            f'<ValCurs Date="{day}" name="Foreign Currency Market">'
            f'<Valute ID="R01235"><NumCode>840</NumCode><CharCode>USD</CharCode>'
            f'<Nominal>1</Nominal><Name>Доллар США</Name><Value>{usd}</Value></Valute>'
            f'<Valute ID="R01239"><NumCode>978</NumCode><CharCode>EUR</CharCode>'
            f'<Nominal>1</Nominal><Name>Евро</Name><Value>{eur}</Value></Valute>'
            f'<Valute ID="R01375"><NumCode>156</NumCode><CharCode>CNY</CharCode>'
            f'<Nominal>10</Nominal><Name>Юань</Name><Value>113,5</Value></Valute>'
            f'</ValCurs>').encode("windows-1251")


class _Answer(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


dialled = []


def fake_open(request, timeout=None):
    url = request.full_url if hasattr(request, "full_url") else str(request)
    dialled.append(url)
    if "date_req=29/09/2026" in url:
        return _Answer(bank_page("29.09.2026", "81,5000", "95,0000"))
    return _Answer(bank_page("30.09.2026", "82,1234", "94,5000"))


parsed, dated = rates.parse_bank(bank_page("30.09.2026", "82,1234", "94,5000")
                                 .decode("windows-1251"))
check("документ банка разобран: запятая, номинал, дата",
      abs(parsed.get("USD", 0) - 82.1234) < 1e-6 and "CNY" not in parsed
      and str(dated) == "2026-09-30", f"| {parsed} {dated}")

real_open = urllib.request.urlopen
urllib.request.urlopen = fake_open
try:
    plugin = rates.RatesPlugin.__new__(rates.RatesPlugin)
    plugin._rates, plugin._asked_at, plugin._asking, plugin._trouble = {}, 0.0, False, ""
    plugin._dated = None
    plugin.log = lambda *a, **k: None
    plugin._fetch()
    fragment = plugin._said()
finally:
    urllib.request.urlopen = real_open
hosts = sorted({url.split("/")[2] for url in dialled})
check("запросы только к www.cbr.ru", hosts == ["www.cbr.ru"], f"| {hosts}")
check("вчерашний курс спрошен за день до даты документа",
      any("date_req=29/09/2026" in url for url in dialled), f"| {dialled}")
check("и стал стрелкой: сегодня и вчера рядом",
      plugin._rates.get("USD") == (82.1234, 81.5)
      and plugin._rates.get("EUR") == (94.5, 95.0), f"| {plugin._rates}")

# 4.0b-K07: from an example to what ships.
print()
print("=== «Курс» как продукт (4.0b-K07) ===")
check("ответ блока встаёт во фразу",
      fragment == "доллар 82,12 рубля, евро 94,50 рубля", f"| {fragment!r}")
check("плитка называет дату курса", plugin._caption() ==
      "Центробанк, курс на 30 сентября", f"| {plugin._caption()}")
declared = plugin.tools()[0]
check("инструмент — читающий блок «Курс валют»",
      declared.reads and declared.title == "Курс валют")


def no_network(request, timeout=None):
    raise OSError("нет сети")


urllib.request.urlopen = no_network
try:
    plugin._asked_at -= rates.FRESH_FOR + 60
    stale = plugin._said()
    check("без сети — последний курс, с датой, на которую он",
          stale == "доллар 82,12 рубля, евро 94,50 рубля (курс на 30 сентября)",
          f"| {stale!r}")
    check("и плитка говорит, что связи нет",
          plugin._caption().endswith("— нет связи"), f"| {plugin._caption()}")

    from plugins.api import ToolFailed

    empty = rates.RatesPlugin.__new__(rates.RatesPlugin)
    empty._rates, empty._asked_at, empty._asking, empty._trouble = {}, 0.0, False, ""
    empty._dated = None
    empty.log = lambda *a, **k: None
    try:
        empty._said()
        check("без сети и без курса — отказ словами, а не «успех»", False)
    except ToolFailed as refusal:
        check("без сети и без курса — отказ словами, а не «успех»",
              "нет связи" in str(refusal), f"| {refusal}")
finally:
    urllib.request.urlopen = real_open
manifest = json.load(io.open(os.path.join(plugins_dir(), "rates", "plugin.json"),
                             encoding="utf-8"))
source_text = io.open(os.path.join(plugins_dir(), "rates", "main.py"),
                      encoding="utf-8").read()
check("описание плагина больше не называет его примером",
      "пример" not in manifest["description"].lower()
      and "simpler of the two examples" not in source_text,
      f"| {manifest['description']}")

print()
print("ИТОГО ошибок:", fails)
sys.exit(1 if fails else 0)
