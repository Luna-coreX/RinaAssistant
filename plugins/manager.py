"""
The plugin manager: discovery, loading, switching on and off, dispatch.

Robustness against errors is the priority: a broken or crashing plugin must
not drop the application. Any error while loading or calling a hook is
caught and written to the plugin's log, and the plugin itself is marked
broken.
"""

import os
import re
import sys
import json
import importlib.util
import inspect
import traceback

from core.i18n import t as tr
from core.logging_setup import get_logger, security_log
from plugins.api import Plugin, PluginManifest, PluginContext, API_VERSION
from core.settings_store import settings


log = get_logger("plugins")


def plugins_dir() -> str:
    """The plugins' directory (next to the project)."""
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(here, "plugins")
    os.makedirs(path, exist_ok=True)
    return path


class PluginInstallError(Exception):
    """The folder or archive does not look like a plugin."""


# A plugin's name becomes the folder's name, so we allow only a plain name:
# letters, digits, "_", "-", a dot inside. No path separators, no "."/"..".
_PLUGIN_ID_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._-]*$")


def _safe_plugin_id(raw):
    """A checked plugin name, or PluginInstallError."""
    plugin_id = re.sub(r"[^\w.-]+", "_", str(raw or "").strip())
    if (not plugin_id or plugin_id in (".", "..")
            or not _PLUGIN_ID_RE.match(plugin_id)):
        security_log().warning("Отклонено имя плагина из plugin.json: %r", raw)
        raise PluginInstallError(tr("Недопустимое имя плагина в plugin.json"))
    return plugin_id


def install_plugin(source_path):
    """
    Installs a plugin from a folder or a .zip into the plugins/ directory.

    We check the contents before copying: the manifest and main.py are
    required, or the plugins directory will gain rubbish that will show up
    as a broken plugin on every start.
    Returns the id of the installed plugin.
    """
    import shutil
    import zipfile
    import tempfile

    source_path = str(source_path or "").strip()
    if not source_path or not os.path.exists(source_path):
        raise PluginInstallError(tr("Файл или папка не найдены"))

    with tempfile.TemporaryDirectory() as tmp:
        if os.path.isdir(source_path):
            staged = source_path
        elif source_path.lower().endswith(".zip"):
            try:
                with zipfile.ZipFile(source_path) as archive:
                    archive.extractall(tmp)
            except (zipfile.BadZipFile, OSError) as e:
                raise PluginInstallError(tr("Не удалось распаковать архив: ") + str(e))
            staged = _find_plugin_root(tmp)
        else:
            raise PluginInstallError(tr("Нужна папка плагина или .zip"))

        if staged is None or not os.path.isfile(os.path.join(staged, "plugin.json")):
            raise PluginInstallError(tr("В плагине нет файла plugin.json"))
        if not os.path.isfile(os.path.join(staged, "main.py")):
            raise PluginInstallError(tr("В плагине нет файла main.py"))

        try:
            with open(os.path.join(staged, "plugin.json"), "r", encoding="utf-8") as f:
                manifest = json.load(f)
        except (OSError, ValueError) as e:
            raise PluginInstallError(tr("Битый plugin.json: ") + str(e))

        plugin_id = _safe_plugin_id(manifest.get("id") or manifest.get("name"))

        base = os.path.abspath(plugins_dir())
        target = os.path.abspath(os.path.join(base, plugin_id))
        # The name is taken from somebody else's file, so we check the
        # result rather than only the original string: the path is obliged
        # to stay directly inside the plugins directory.
        if os.path.dirname(target) != base or target == base:
            security_log().warning(
                "Путь установки плагина ведёт за пределы каталога: %s", target)
            raise PluginInstallError(tr("Недопустимое имя плагина в plugin.json"))
        if os.path.abspath(staged) == target:
            raise PluginInstallError(tr("Этот плагин уже установлен"))
        replaced = os.path.isdir(target)
        if replaced:
            # updating over the top: we delete only what is itself a plugin
            if not os.path.isfile(os.path.join(target, "plugin.json")):
                raise PluginInstallError(tr("В папке назначения не плагин"))
            shutil.rmtree(target, ignore_errors=True)
        shutil.copytree(staged, target)

    if replaced:
        # There already was a plugin under this id, and it may have been
        # switched on. A new plugin's code runs when it is switched on, so we
        # do not inherit somebody else's "on": otherwise a slipped-in archive
        # with somebody else's id would run by itself, without the user
        # knowing. Let them switch it on deliberately.
        _disable_saved(plugin_id)
        security_log().warning(
            "Плагин %s заменён установкой из %s и принудительно выключен",
            plugin_id, source_path)
    else:
        security_log().info("Установлен плагин %s из %s",
                            plugin_id, source_path)
    return plugin_id, replaced


def _disable_saved(plugin_id):
    """Removes a plugin from the list of switched-on ones in the settings."""
    enabled = [p for p in (settings.get("enabled_plugins", []) or [])
               if p != plugin_id]
    settings.set("enabled_plugins", enabled)
    settings.save()


def _find_plugin_root(base):
    """Looks for the folder with plugin.json — an archive often holds one nested folder."""
    if os.path.isfile(os.path.join(base, "plugin.json")):
        return base
    for name in sorted(os.listdir(base)):
        candidate = os.path.join(base, name)
        if os.path.isdir(candidate) and \
                os.path.isfile(os.path.join(candidate, "plugin.json")):
            return candidate
    return None


class LoadedPlugin:
    """A wrapper around a plugin's instance plus its state."""
    def __init__(self, manifest: PluginManifest):
        self.manifest = manifest
        self.instance = None      # the Plugin instance (if loaded)
        self.enabled = False
        self.error = None         # the error text, if it failed
        self.logs = []            # the log's last lines


class Signal:
    """
    Notifying subscribers. A stand-in for `PySide6.QtCore.Signal`.

    The plugin manager lived in an application with a window and notified it
    with Qt signals. In 4.0 the plugins belong to the **core**, and the core
    is obliged to work where there is no interface library at all
    (`rina_core.check_headless`): one transitive import of Qt and the split
    is broken.

    The surface is preserved deliberately — `connect` and `emit` — so that
    the 3.1.0 application goes on working without changes on its side. The
    difference is that the call happens **in the same thread** rather than
    through the window's event queue: the core has no window queue, and it
    matters more to a subscriber to get the notification than to get it in
    somebody else's thread.
    """

    def __init__(self, *types):
        self._types = types
        self._listeners = []

    def connect(self, listener):
        if listener not in self._listeners:
            self._listeners.append(listener)
        return listener

    def disconnect(self, listener=None):
        if listener is None:
            self._listeners.clear()
        elif listener in self._listeners:
            self._listeners.remove(listener)

    def emit(self, *args):
        # A subscriber that dropped its handler must not cut off the
        # notification to the rest: the plugin has already shown that it can
        # be unreliable, and burying half the subscribers with it is not
        # what we want.
        for listener in list(self._listeners):
            try:
                listener(*args)
            except Exception:                            # noqa: BLE001
                log.exception("Подписчик сигнала уронил обработчик")


class PluginManager:
    def __init__(self, parent=None):
        # The signals belong to each manager rather than being shared by
        # the class: in Qt they were declared in the class body but bound to
        # the instance. Leaving them in the body here would mean two
        # managers sharing subscribers.
        self.changed = Signal()               # the list/state changed
        self.log_added = Signal(str, str)     # (plugin_id, message)
        self.response = Signal(str, str)      # the plugin said something
        self.pages_changed = Signal()         # the set of tabs changed
        self.window_requested = Signal(str, object, str, int, int)
        self.notify_requested = Signal(str, str, str)
        self.plugins = {}   # id -> LoadedPlugin

    # ---------- discovery ----------
    def discover(self):
        """Scans the plugins directory and reads the manifests (without loading code)."""
        self.plugins.clear()
        base = plugins_dir()
        enabled_ids = set(settings.get("enabled_plugins", []) or [])

        for name in sorted(os.listdir(base)):
            folder = os.path.join(base, name)
            manifest_path = os.path.join(folder, "plugin.json")
            if not os.path.isdir(folder) or not os.path.isfile(manifest_path):
                continue
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                manifest = PluginManifest.from_dict(data, path=folder)
                # The folder's name is the only reliable identifier: the id
                # inside plugin.json is written by the plugin's author, and
                # a clash with somebody else's id would hand them that
                # plugin's settings and its place in the list.
                manifest.id = name
            except Exception as e:
                # a broken manifest — we show it as a broken plugin
                manifest = PluginManifest(id=name, name=name, path=folder)
                lp = LoadedPlugin(manifest)
                lp.error = f"Ошибка манифеста: {e}"
                self.plugins[manifest.id] = lp
                continue

            lp = LoadedPlugin(manifest)
            # the API compatibility check
            if not manifest.api_compatible():
                # The reason, the version and what to do, in one sentence
                # (4.0-H05). A silent "it does not work" looks like a
                # breakage in Rina rather than an outdated plugin.
                lp.error = manifest.why_incompatible()
            self.plugins[manifest.id] = lp

        broken = [p.manifest.id for p in self.plugins.values() if p.error]
        log.info("Найдено плагинов: %d, из них сбойных: %d",
                 len(self.plugins), len(broken))
        for pid in broken:
            log.warning("Плагин «%s»: %s", pid, self.plugins[pid].error)

        # we switch on the ones that were on before
        for pid in enabled_ids:
            if pid in self.plugins:
                self.enable(pid, persist=False)

        self.changed.emit()

    # ---------- loading the code ----------
    def _load_instance(self, lp: LoadedPlugin) -> bool:
        manifest = lp.manifest
        main_py = os.path.join(manifest.path, "main.py")
        if not os.path.isfile(main_py):
            lp.error = tr("Нет файла main.py")
            return False

        mod_name = f"rina_plugin_{manifest.id}"
        try:
            spec = importlib.util.spec_from_file_location(mod_name, main_py)
            module = importlib.util.module_from_spec(spec)
            sys.modules[mod_name] = module
            spec.loader.exec_module(module)
        except Exception:
            lp.error = tr("Ошибка импорта:\n") + traceback.format_exc(limit=3)
            return False

        # we find the plugin's class
        plugin_cls = None
        if manifest.entry:
            plugin_cls = getattr(module, manifest.entry, None)
        if plugin_cls is None:
            for _, obj in inspect.getmembers(module, inspect.isclass):
                if issubclass(obj, Plugin) and obj is not Plugin:
                    plugin_cls = obj
                    break
        if plugin_cls is None:
            lp.error = tr("Не найден класс, наследующий Plugin")
            return False

        try:
            ctx = PluginContext(manifest, self)
            lp.instance = plugin_cls(ctx)
            lp.error = None
            return True
        except Exception:
            lp.error = tr("Ошибка инициализации:\n") + traceback.format_exc(limit=3)
            return False

    # ---------- switching on / off ----------
    def enable(self, plugin_id: str, persist=True):
        lp = self.plugins.get(plugin_id)
        if not lp or lp.enabled:
            return
        # we do not switch on ones incompatible by API
        if not lp.manifest.api_compatible():
            self.changed.emit()
            return
        if lp.instance is None:
            if not self._load_instance(lp):
                self.changed.emit()
                return
        lp.enabled = True
        log.info("Плагин включён: %s", plugin_id)
        self._safe_call(lp, "on_enable")
        if persist:
            self._persist_enabled()
        self.changed.emit()
        self.pages_changed.emit()

    def disable(self, plugin_id: str, persist=True):
        lp = self.plugins.get(plugin_id)
        if not lp or not lp.enabled:
            return
        self._safe_call(lp, "on_disable")
        lp.enabled = False
        log.info("Плагин выключен: %s", plugin_id)
        if persist:
            self._persist_enabled()
        self.changed.emit()
        self.pages_changed.emit()

    def toggle(self, plugin_id: str, on: bool):
        if on:
            self.enable(plugin_id)
        else:
            self.disable(plugin_id)

    def _persist_enabled(self):
        ids = [pid for pid, lp in self.plugins.items() if lp.enabled]
        settings.set("enabled_plugins", ids)
        settings.save()

    # ---------- dispatch ----------
    def dispatch_command(self, text: str) -> bool:
        """Runs a command past the switched-on plugins. True if somebody handled it."""
        for lp in self.plugins.values():
            if lp.enabled and lp.instance is not None:
                try:
                    if lp.instance.on_command(text):
                        return True
                except Exception:
                    self.log(lp.manifest.id,
                             tr("Ошибка on_command:\n") + traceback.format_exc(limit=2))
        return False

    def broadcast_event(self, name: str, data: dict = None):
        for lp in self.plugins.values():
            if lp.enabled and lp.instance is not None:
                self._safe_call(lp, "on_event", name, data or {})

    def _safe_call(self, lp: LoadedPlugin, method: str, *args):
        fn = getattr(lp.instance, method, None)
        if fn is None:
            return
        try:
            fn(*args)
        except Exception:
            self.log(lp.manifest.id,
                     f"Ошибка {method}:\n" + traceback.format_exc(limit=2))

    # ---------- services for plugins (PluginContext) ----------
    def log(self, plugin_id: str, message: str):
        lp = self.plugins.get(plugin_id)
        if lp is not None:
            lp.logs.append(message)
            lp.logs = lp.logs[-50:]
        self.log_added.emit(plugin_id, message)

    def respond(self, plugin_id: str, text: str):
        self.response.emit(plugin_id, text)

    def get_plugin_setting(self, plugin_id, key, default=None):
        store = settings.get("plugin_settings", {}) or {}
        return store.get(plugin_id, {}).get(key, default)

    def set_plugin_setting(self, plugin_id, key, value):
        store = settings.get("plugin_settings", {}) or {}
        store.setdefault(plugin_id, {})[key] = value
        settings.set("plugin_settings", store)
        settings.save()

    def open_plugin_window(self, plugin_id, widget, title, width, height):
        # the UI thread will pick the signal up and create the window
        self.window_requested.emit(plugin_id, widget, title, width, height)

    def notify_from_plugin(self, plugin_id, title, message):
        self.notify_requested.emit(plugin_id, title, message)

    # ---------- access to plugins' tabs ----------
    def page_plugins(self):
        """
        A list of (plugin_id, LoadedPlugin) of switched-on plugins with a
        page. The order is stable.
        """
        result = []
        for pid, lp in self.plugins.items():
            if lp.enabled and lp.instance is not None:
                try:
                    if self._has_page(lp):
                        result.append((pid, lp))
                except Exception:
                    pass
        return result

    def _has_page(self, lp):
        # There is a page if `page()` is overridden. We check it "cheaply":
        # does the method differ from the base one. `create_page` is not
        # considered at all any more — a plugin that gives out a widget does
        # not load (4.0-H05).
        return type(lp.instance).page is not Plugin.page

    # ---------- the declared tools (4.0-H03) ----------
    def tool_prefix(self, plugin_id):
        """
        Under what name a plugin's tools live in the registry.

        The prefix is obligatory: two plugins with a `roll` tool would
        otherwise fight over one name, and whichever was switched on later
        would win.
        """
        return f"plugin.{plugin_id}."

    def declared_tools(self, plugin_id):
        """
        What the plugin declared — already with checked permissions.

        Returns a list of `(Tool, run)`: the first is the description for
        the core's registry, the second is what to call. A tool asking for
        what a plugin may not have (ADR 0010) is **not created at all**: it
        would refuse anyway, but only after the person had seen it and
        called it.
        """
        from core.permissions import plugin_allowed
        from core.tools import Tool

        lp = self.plugins.get(plugin_id)
        if not lp or lp.instance is None:
            return []

        declared = []
        try:
            declared = list(lp.instance.tools() or [])
        except Exception:                                # noqa: BLE001
            self.log(plugin_id,
                     tr("Ошибка tools:\n") + traceback.format_exc(limit=2))
            return []

        allowed_by_manifest, refused = plugin_allowed(lp.manifest.permissions)
        if refused:
            self.log(plugin_id,
                     "Не выдано разрешений: " + ", ".join(refused))

        made = []
        for one in declared:
            wanted = set(str(p) for p in (one.permissions or ()))
            if not wanted.issubset(set(allowed_by_manifest)):
                self.log(plugin_id,
                         f"Инструмент «{one.name}» не заведён: просит "
                         f"{sorted(wanted - set(allowed_by_manifest))}")
                continue
            try:
                tool = Tool(
                    name=self.tool_prefix(plugin_id) + str(one.name),
                    summary=str(one.summary),
                    params=tuple(one.params or ()),
                    permissions=frozenset(wanted),
                    confirm_required=bool(one.confirm_required),
                )
            except Exception:                            # noqa: BLE001
                self.log(plugin_id,
                         tr("Ошибка tools:\n") + traceback.format_exc(limit=2))
                continue
            made.append((tool, self._wrap(plugin_id, one)))
        return made

    def _wrap(self, plugin_id, declared):
        """
        A wrapper around a call into the plugin.

        A plugin is unreliable by definition — it is somebody else's code —
        so its exception turns into a tool's failure rather than into the
        core falling over. And it is written to the plugin's log: the author
        needs to learn what broke, and the person that it did not work.
        """
        from core.toolrunner import ToolResult

        def run(ctx, args):
            try:
                answer = declared.run(args) if declared.run else None
            except Exception:                            # noqa: BLE001
                self.log(plugin_id,
                         tr("Ошибка инструмента:\n")
                         + traceback.format_exc(limit=3))
                return ToolResult.failed(
                    tr("Плагин не справился."), "internal")
            if isinstance(answer, ToolResult):
                return answer
            return ToolResult.done(str(answer) if answer is not None else "")

        return run

    def get_plugin_page_spec(self, plugin_id):
        """The declarative description of a tab (a list of elements), or []."""
        lp = self.plugins.get(plugin_id)
        if not lp or lp.instance is None:
            return []
        try:
            return lp.instance.page() or []
        except Exception:
            self.log(plugin_id,
                     tr("Ошибка page:\n") + traceback.format_exc(limit=2))
            return []

    def dispatch_action(self, plugin_id, action, value=None):
        """A button on the plugin's tab was pressed."""
        lp = self.plugins.get(plugin_id)
        if not lp or lp.instance is None:
            return
        self._safe_call(lp, "on_action", action, value)

    def plugin_page_meta(self, plugin_id):
        """(title, icon) for the plugin's tab."""
        lp = self.plugins.get(plugin_id)
        if not lp:
            return (plugin_id, "🧩")
        inst = lp.instance
        title = getattr(inst, "page_title", None) or lp.manifest.name
        icon = getattr(inst, "page_icon", None) or lp.manifest.icon
        return (title, icon)

    def has_settings_schema(self, lp):
        inst = lp.instance
        if inst is None:
            return False
        return type(inst).settings_schema is not Plugin.settings_schema

    def get_settings_schema(self, plugin_id):
        lp = self.plugins.get(plugin_id)
        if not lp or lp.instance is None:
            return []
        try:
            return lp.instance.settings_schema() or []
        except Exception:
            return []


# one instance
plugin_manager = PluginManager()
