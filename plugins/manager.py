"""
Менеджер плагинов: обнаружение, загрузка, включение/выключение, диспетчеризация.

Устойчивость к ошибкам — приоритет: битый или падающий плагин не должен
ронять приложение. Любая ошибка при загрузке/вызове хука ловится и пишется
в лог плагина, сам плагин помечается как сбойный.
"""

import os
import re
import sys
import json
import importlib.util
import inspect
import traceback

from PySide6.QtCore import QObject, Signal

from core.i18n import t as tr
from plugins.api import Plugin, PluginManifest, PluginContext, API_VERSION
from core.settings_store import settings


def plugins_dir() -> str:
    """Каталог с плагинами (рядом с проектом)."""
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(here, "plugins")
    os.makedirs(path, exist_ok=True)
    return path


class PluginInstallError(Exception):
    """Папка или архив не похожи на плагин."""


# Имя плагина становится именем папки, поэтому допускаем только простое имя:
# буквы, цифры, «_», «-», точка внутри. Ни разделителей пути, ни «.»/«..».
_PLUGIN_ID_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._-]*$")


def _safe_plugin_id(raw):
    """Проверенное имя плагина или PluginInstallError."""
    plugin_id = re.sub(r"[^\w.-]+", "_", str(raw or "").strip())
    if (not plugin_id or plugin_id in (".", "..")
            or not _PLUGIN_ID_RE.match(plugin_id)):
        raise PluginInstallError(tr("Недопустимое имя плагина в plugin.json"))
    return plugin_id


def install_plugin(source_path):
    """
    Устанавливает плагин из папки или .zip в каталог plugins/.

    Проверяем содержимое до копирования: манифест и main.py обязательны,
    иначе в каталоге плагинов появится мусор, который каждый запуск будет
    показываться как сбойный плагин.
    Возвращает id установленного плагина.
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
        # Имя берётся из чужого файла, поэтому проверяем результат, а не только
        # исходную строку: путь обязан остаться прямо внутри каталога плагинов.
        if os.path.dirname(target) != base or target == base:
            raise PluginInstallError(tr("Недопустимое имя плагина в plugin.json"))
        if os.path.abspath(staged) == target:
            raise PluginInstallError(tr("Этот плагин уже установлен"))
        replaced = os.path.isdir(target)
        if replaced:
            # обновление поверх: удаляем только то, что само является плагином
            if not os.path.isfile(os.path.join(target, "plugin.json")):
                raise PluginInstallError(tr("В папке назначения не плагин"))
            shutil.rmtree(target, ignore_errors=True)
        shutil.copytree(staged, target)

    if replaced:
        # Под этим id уже был плагин, и он мог быть включён. Код нового плагина
        # выполняется при включении, поэтому не наследуем чужое «включено»:
        # иначе подсунутый архив с чужим id запускался бы сам, без ведома
        # пользователя. Пусть включит осознанно.
        _disable_saved(plugin_id)
    return plugin_id, replaced


def _disable_saved(plugin_id):
    """Убирает плагин из списка включённых в настройках."""
    enabled = [p for p in (settings.get("enabled_plugins", []) or [])
               if p != plugin_id]
    settings.set("enabled_plugins", enabled)
    settings.save()


def _find_plugin_root(base):
    """Ищет папку с plugin.json — архив часто содержит одну вложенную папку."""
    if os.path.isfile(os.path.join(base, "plugin.json")):
        return base
    for name in sorted(os.listdir(base)):
        candidate = os.path.join(base, name)
        if os.path.isdir(candidate) and \
                os.path.isfile(os.path.join(candidate, "plugin.json")):
            return candidate
    return None


class LoadedPlugin:
    """Обёртка над экземпляром плагина + его состояние."""
    def __init__(self, manifest: PluginManifest):
        self.manifest = manifest
        self.instance = None      # экземпляр Plugin (если загружен)
        self.enabled = False
        self.error = None         # текст ошибки, если сбой
        self.logs = []            # последние строки лога


class PluginManager(QObject):
    # сигналы для UI
    changed = Signal()                    # список/состояние изменились
    log_added = Signal(str, str)          # (plugin_id, message)
    response = Signal(str, str)           # (plugin_id, text) — плагин что-то ответил
    pages_changed = Signal()              # набор вкладок плагинов изменился
    window_requested = Signal(str, object, str, int, int)  # (pid, widget, title, w, h)
    notify_requested = Signal(str, str, str)   # (pid, title, message)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.plugins = {}   # id -> LoadedPlugin

    # ---------- обнаружение ----------
    def discover(self):
        """Сканирует каталог плагинов и читает манифесты (без загрузки кода)."""
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
                # Имя папки — единственный надёжный идентификатор: id внутри
                # plugin.json пишет автор плагина, и совпадение с чужим id
                # отдало бы ему настройки и место соседа в списке.
                manifest.id = name
            except Exception as e:
                # битый манифест — показываем как сбойный плагин
                manifest = PluginManifest(id=name, name=name, path=folder)
                lp = LoadedPlugin(manifest)
                lp.error = f"Ошибка манифеста: {e}"
                self.plugins[manifest.id] = lp
                continue

            lp = LoadedPlugin(manifest)
            # проверка совместимости API
            if not manifest.api_compatible():
                lp.error = (f"Плагину нужна версия API {manifest.api_version}, "
                            f"а приложение поддерживает до {API_VERSION}. "
                            f"Обновите приложение.")
            self.plugins[manifest.id] = lp

        # включаем те, что были включены ранее
        for pid in enabled_ids:
            if pid in self.plugins:
                self.enable(pid, persist=False)

        self.changed.emit()

    # ---------- загрузка кода ----------
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

        # находим класс плагина
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

    # ---------- включение / выключение ----------
    def enable(self, plugin_id: str, persist=True):
        lp = self.plugins.get(plugin_id)
        if not lp or lp.enabled:
            return
        # несовместимые по API не включаем
        if not lp.manifest.api_compatible():
            self.changed.emit()
            return
        if lp.instance is None:
            if not self._load_instance(lp):
                self.changed.emit()
                return
        lp.enabled = True
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

    # ---------- диспетчеризация ----------
    def dispatch_command(self, text: str) -> bool:
        """Прогоняет команду по включённым плагинам. True если кто-то обработал."""
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

    # ---------- сервисы для плагинов (PluginContext) ----------
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
        # UI-поток подхватит сигнал и создаст окно
        self.window_requested.emit(plugin_id, widget, title, width, height)

    def notify_from_plugin(self, plugin_id, title, message):
        self.notify_requested.emit(plugin_id, title, message)

    # ---------- доступ к вкладкам плагинов ----------
    def page_plugins(self):
        """
        Список (plugin_id, LoadedPlugin) включённых плагинов, у которых есть
        своя вкладка (create_page вернул виджет). Порядок стабильный.
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
        # вкладка есть, если переопределён page() (API v2) или create_page() (v1).
        # Проверяем «дёшево»: отличается ли метод от базового.
        cls = type(lp.instance)
        return (cls.page is not Plugin.page
                or cls.create_page is not Plugin.create_page)

    def get_plugin_page_spec(self, plugin_id):
        """Декларативное описание вкладки (список элементов) или []."""
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
        """Нажата кнопка на вкладке плагина."""
        lp = self.plugins.get(plugin_id)
        if not lp or lp.instance is None:
            return
        self._safe_call(lp, "on_action", action, value)

    def build_plugin_page(self, plugin_id):
        """Создать виджет вкладки плагина (или None)."""
        lp = self.plugins.get(plugin_id)
        if not lp or lp.instance is None:
            return None

        # API v2: плагин описывает страницу, рисуем её сами
        if type(lp.instance).page is not Plugin.page:
            try:
                from plugins.page_view import PluginPageView
                return PluginPageView(plugin_id, self)
            except Exception:
                self.log(plugin_id,
                         tr("Ошибка page:\n") + traceback.format_exc(limit=2))
                return None

        # API v1: устаревший путь с готовым QWidget
        try:
            return lp.instance.create_page()
        except Exception:
            self.log(plugin_id, tr("Ошибка create_page:\n") + traceback.format_exc(limit=2))
            return None

    def plugin_page_meta(self, plugin_id):
        """(title, icon) для вкладки плагина."""
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


# единый экземпляр
plugin_manager = PluginManager()
