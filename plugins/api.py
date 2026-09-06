"""
Rina's public plugin API. Version 4.

Every plugin is a folder in plugins/ with a plugin.json (the manifest) and a
main.py (a class inheriting from Plugin). The class is found by the
manifest's "entry" field, or automatically (the first subclass of Plugin).

**A plugin declares rather than does.** The decision is
[ADR 0010](../docs/adr/0010-plugin-api.md). It declares three things, and
all three as data:

  - **tools** (`tools()`) — what it can do; they go into the core's registry
    and get permissions, confirmations and journalling there on a par with
    the built-in ones;
  - **a page** (`page()`) — how it looks; as a description by the version 2
    schema (`plugins/page_spec.py`), without widgets;
  - **permissions** — what it needs from the machine; as a list in the
    manifest, before the first run.

Why: the core asks a person for consent to "launching programs" and refuses
without it, while a plugin beside it could call `subprocess` and ask
nothing. While the plugins were three demonstrations, that was a theoretical
hole; with third-party ones it becomes the only one that matters.

A plugin's capabilities (every hook is optional):
  - on_enable / on_disable         — the life cycle
  - on_command(text) -> bool       — handling a command
  - on_event(name, data)           — arbitrary events
  - tools() -> [PluginTool]        — the declared tools (v4)
  - page() -> [Element]            — a page of its own, as a description
  - on_action(action, value)       — a button on the page was pressed
  - settings_schema() -> [Field]   — declarative settings

Through self.ctx the application's services are available:
  - respond(text)                  — Rina will speak/show the text
  - log(msg)                       — the plugin's log
  - get_setting/set_setting        — its own settings (kept in the config)
  - notify(title, message)         — a notification (the tray)

What is **gone**: `create_page()` and `open_window()`. A ready-made widget
tied the core to a particular shell — that was a direct blocker of the
process split. A version 1-3 plugin does not load, and the person is told
why (`4.0-H05`).

Compatibility: the manifest states "api_version". The current one is
API_VERSION.
"""

from dataclasses import dataclass, field


#: The plugin API's version. Grows on incompatible changes.
#:
#: 4 — a plugin declares tools and a page; `create_page` is gone.
API_VERSION = 4

#: The lowest version the core still loads.
#:
#: It deliberately coincides with the current one: a plugin that gives out a
#: widget cannot be "partly supported" — a C# shell will not draw a
#: `QWidget` in any way at all.
MIN_API_VERSION = 4


@dataclass
class PluginManifest:
    id: str
    name: str
    version: str = "1.0.0"
    author: str = "unknown"
    description: str = ""
    entry: str = ""
    icon: str = "🧩"
    path: str = ""
    api_version: int = 1     # which API version the plugin expects
    #: What the plugin asks of the machine (`4.0-H06`). The names come from
    #: the `core/permissions.py` catalogue; a second catalogue "for plugins"
    #: would mean two languages about one and the same thing. Not all of it
    #: is available: see ADR 0010.
    permissions: tuple = ()

    @staticmethod
    def from_dict(d: dict, path: str = "") -> "PluginManifest":
        return PluginManifest(
            id=str(d.get("id") or d.get("name", "")).strip(),
            name=str(d.get("name", d.get("id", "Без имени"))),
            version=str(d.get("version", "1.0.0")),
            author=str(d.get("author", "unknown")),
            description=str(d.get("description", "")),
            entry=str(d.get("entry", "")),
            icon=str(d.get("icon", "🧩")),
            path=path,
            api_version=int(d.get("api_version", 1)),
            permissions=tuple(str(p) for p in (d.get("permissions") or ())),
        )

    def api_compatible(self) -> bool:
        """Do we load such a plugin at all."""
        return MIN_API_VERSION <= self.api_version <= API_VERSION

    def why_incompatible(self) -> str:
        """
        Why it was not loaded — in human words (`4.0-H05`).

        A silent "the plugin simply does not work" looks like a breakage in
        Rina rather than an outdated plugin. So the reason, the version and
        what the author should do are all named.
        """
        if self.api_version > API_VERSION:
            return (f"Плагину нужна версия API {self.api_version}, "
                    f"а эта сборка поддерживает {API_VERSION}. "
                    f"Обновите Рину.")
        return (f"Плагин написан под API {self.api_version}, а нужна "
                f"версия {API_VERSION}: страница описывается методом "
                f"page(), а не create_page(). Обновите плагин.")


@dataclass
class PluginTool:
    """
    A tool declared by a plugin.

    It goes into the core's registry under the name `plugin.<id>.<name>` and
    gets exactly the same gates there as a built-in one: the permission
    check, confirmation of the irreversible, a journal entry saying which
    plugin started this.

    `run(args)` is called by the core, not by the plugin: a plugin does not
    decide when its tool works — it declared what it can do and waits.
    """

    name: str
    summary: str
    run: object = None
    #: The arguments — by the same `Param` as the built-in tools'.
    params: tuple = ()
    #: What has to be allowed. An empty set means nothing.
    permissions: tuple = ()
    #: Ask the person on every call.
    confirm_required: bool = False


class PluginContext:
    """
    A layer between the plugin and the application. A plugin depends only on
    it, not on the UI's innards.
    """

    def __init__(self, manifest: PluginManifest, host):
        self.manifest = manifest
        self._host = host  # PluginManager

    def log(self, message: str):
        self._host.log(self.manifest.id, str(message))

    def respond(self, text: str):
        """Rina will speak/show the text."""
        self._host.respond(self.manifest.id, str(text))

    def get_setting(self, key: str, default=None):
        return self._host.get_plugin_setting(self.manifest.id, key, default)

    def set_setting(self, key: str, value):
        self._host.set_plugin_setting(self.manifest.id, key, value)

    def notify(self, title, message):
        """Show a notification (through the tray, if it is available)."""
        self._host.notify_from_plugin(self.manifest.id, title, message)


class Plugin:
    """
    A plugin's base class. Subclasses override the hooks they need.
    """

    # the tab's title/icon (if the plugin gives out create_page)
    page_title = None    # by default the name from the manifest is taken
    page_icon = None     # by default the icon from the manifest

    def __init__(self, context: PluginContext):
        self.ctx = context
        self.manifest = context.manifest

    # --- convenient proxies ---
    def log(self, message):
        self.ctx.log(message)

    def respond(self, text):
        self.ctx.respond(text)

    # --- the life-cycle hooks ---
    def on_enable(self):
        pass

    def on_disable(self):
        pass

    def on_command(self, text: str) -> bool:
        return False

    def on_event(self, name: str, data: dict = None):
        pass

    # --- UI extensions (optional) ---
    def page(self):
        """
        Describe your own tab as a list of elements (see
        plugins/page_spec.py). The application draws it itself, so the
        plugin does not depend on Qt and will not break when the shell
        changes. [] or None means there is no tab.

        This is the recommended way (API v2).
        """
        return None

    def on_action(self, action: str, value=None):
        """
        A button with this action on the plugin's tab was pressed.
        After the call the page is rebuilt automatically.
        """
        pass

    def tools(self):
        """
        Declare tools (API v4).

        A list of `PluginTool`. The names inside a plugin are short — the
        core adds the `plugin.<id>.` prefix itself, so that two plugins with
        a `roll` tool do not fight over one name.

        The permissions are checked **before** registration: what a plugin
        is not entitled to (ADR 0010) is not granted, and the tool itself is
        not created — a tool without the permission it needs would refuse
        anyway, but only after the person had seen it and called it.
        """
        return []

    def settings_schema(self):
        """
        Return a list of Field (see ui/plugins/settings_spec.py) — then the
        application builds the plugin's settings panel itself. [] means
        there are no settings.
        """
        return []

    # --- convenient access to one's own settings, respecting the schema ---
    def setting(self, key, default=None):
        # the value from the config, else the schema's default, else the one passed in
        val = self.ctx.get_setting(key, None)
        if val is not None:
            return val
        for f in self.settings_schema() or []:
            if f.key == key:
                return f.default
        return default
