"""
Публичный API плагинов Rina.

Каждый плагин — папка в plugins/ с plugin.json (манифест) и main.py
(класс-наследник Plugin). Класс находится по полю "entry" манифеста
либо автоматически (первый наследник Plugin).

Возможности плагина (все хуки необязательны):
  - on_enable / on_disable         — жизненный цикл
  - on_command(text) -> bool       — обработка команды
  - on_event(name, data)           — произвольные события
  - create_page() -> QWidget|None  — своя ВКЛАДКА в приложении
  - settings_schema() -> [Field]   — декларативные настройки (панель строит app)
  - page_title / page_icon         — как назвать вкладку в сайдбаре

Через self.ctx доступны сервисы приложения:
  - respond(text)                  — Рина озвучит/покажет текст
  - log(msg)                       — лог плагина
  - get_setting/set_setting        — свои настройки (хранятся в конфиге)
  - open_window(widget, title)     — показать доп. окно
  - notify(title, message)         — уведомление (трей)

Совместимость: манифест может указывать "api_version". Текущая версия — API_VERSION.
"""

from dataclasses import dataclass


API_VERSION = 2   # версия API плагинов (растёт при несовместимых изменениях)


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
    api_version: int = 1     # какую версию API ожидает плагин

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
        )

    def api_compatible(self) -> bool:
        # плагин совместим, если его api_version не выше текущей
        return self.api_version <= API_VERSION


class PluginContext:
    """
    Прослойка между плагином и приложением. Плагин зависит только от неё,
    а не от внутренностей UI.
    """

    def __init__(self, manifest: PluginManifest, host):
        self.manifest = manifest
        self._host = host  # PluginManager

    def log(self, message: str):
        self._host.log(self.manifest.id, str(message))

    def respond(self, text: str):
        """Рина озвучит/покажет текст."""
        self._host.respond(self.manifest.id, str(text))

    def get_setting(self, key: str, default=None):
        return self._host.get_plugin_setting(self.manifest.id, key, default)

    def set_setting(self, key: str, value):
        self._host.set_plugin_setting(self.manifest.id, key, value)

    def open_window(self, widget, title="", width=420, height=320):
        """Показать дополнительное окно с содержимым widget."""
        return self._host.open_plugin_window(
            self.manifest.id, widget, title or self.manifest.name, width, height)

    def notify(self, title, message):
        """Показать уведомление (через трей, если доступен)."""
        self._host.notify_from_plugin(self.manifest.id, title, message)


class Plugin:
    """
    Базовый класс плагина. Наследники переопределяют нужные хуки.
    """

    # заголовок/иконка вкладки (если плагин отдаёт create_page)
    page_title = None    # по умолчанию берётся имя из манифеста
    page_icon = None     # по умолчанию иконка из манифеста

    def __init__(self, context: PluginContext):
        self.ctx = context
        self.manifest = context.manifest

    # --- удобные прокси ---
    def log(self, message):
        self.ctx.log(message)

    def respond(self, text):
        self.ctx.respond(text)

    # --- хуки жизненного цикла ---
    def on_enable(self):
        pass

    def on_disable(self):
        pass

    def on_command(self, text: str) -> bool:
        return False

    def on_event(self, name: str, data: dict = None):
        pass

    # --- расширения UI (необязательные) ---
    def create_page(self):
        """
        Вернуть QWidget — тогда у плагина появится своя вкладка в сайдбаре.
        None — вкладки нет.
        """
        return None

    def settings_schema(self):
        """
        Вернуть список Field (см. ui/plugins/settings_spec.py) — тогда
        приложение само построит панель настроек плагина. [] — нет настроек.
        """
        return []

    # --- удобный доступ к своим настройкам с учётом схемы ---
    def setting(self, key, default=None):
        # значение из конфига, иначе default из схемы, иначе переданный default
        val = self.ctx.get_setting(key, None)
        if val is not None:
            return val
        for f in self.settings_schema() or []:
            if f.key == key:
                return f.default
        return default
