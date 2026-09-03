"""
Публичный API плагинов Rina. Версия 4.

Каждый плагин — папка в plugins/ с plugin.json (манифест) и main.py
(класс-наследник Plugin). Класс находится по полю "entry" манифеста
либо автоматически (первый наследник Plugin).

**Плагин объявляет, а не делает.** Решение — [ADR 0010]
(../docs/adr/0010-plugin-api.md). Он объявляет три вещи, и все три
данными:

  - **инструменты** (`tools()`) — что он умеет; уходят в реестр ядра и
    получают там разрешения, подтверждения и журнал наравне со
    встроенными;
  - **страницу** (`page()`) — как он выглядит; описанием по схеме версии 2
    (`plugins/page_spec.py`), без виджетов;
  - **разрешения** — что ему нужно от машины; списком в манифесте, до
    первого запуска.

Почему так: ядро спрашивает у человека согласие на «запуск программ» и
отказывает без него, а плагин рядом мог позвать `subprocess` и ничего не
спросить. Пока плагины были три демонстрационных, это была теоретическая
дыра; со сторонними она становится единственной, которая имеет значение.

Возможности плагина (все хуки необязательны):
  - on_enable / on_disable         — жизненный цикл
  - on_command(text) -> bool       — обработка команды
  - on_event(name, data)           — произвольные события
  - tools() -> [PluginTool]        — объявленные инструменты (v4)
  - page() -> [Element]            — своя страница, описанием
  - on_action(action, value)       — нажали кнопку на странице
  - settings_schema() -> [Field]   — декларативные настройки

Через self.ctx доступны сервисы приложения:
  - respond(text)                  — Рина озвучит/покажет текст
  - log(msg)                       — лог плагина
  - get_setting/set_setting        — свои настройки (хранятся в конфиге)
  - notify(title, message)         — уведомление (трей)

Чего **больше нет**: `create_page()` и `open_window()`. Готовый виджет
привязывал ядро к конкретной оболочке — это был прямой блокер разделения
процессов. Плагин версии 1–3 не загружается, и человеку сказано, почему
(`4.0-H05`).

Совместимость: манифест указывает "api_version". Текущая — API_VERSION.
"""

from dataclasses import dataclass, field


#: Версия API плагинов. Растёт при несовместимых изменениях.
#:
#: 4 — плагин объявляет инструменты и страницу; `create_page` убран.
API_VERSION = 4

#: Минимальная версия, которую ядро ещё загружает.
#:
#: Совпадает с текущей нарочно: плагин, отдающий виджет, невозможно
#: «частично поддержать» — оболочка на C# не нарисует `QWidget` никак.
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
    api_version: int = 1     # какую версию API ожидает плагин
    #: Что плагин просит от машины (`4.0-H06`). Имена — из каталога
    #: `core/permissions.py`; второй каталог «для плагинов» означал бы два
    #: языка об одном и том же. Доступно из него не всё: см. ADR 0010.
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
        """Загружаем ли мы такой плагин вовсе."""
        return MIN_API_VERSION <= self.api_version <= API_VERSION

    def why_incompatible(self) -> str:
        """
        Почему не загрузили — человеческими словами (`4.0-H05`).

        Молчаливое «плагин просто не работает» выглядит как поломка Рины,
        а не как устаревший плагин. Поэтому названы и причина, и версия, и
        что автору делать.
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
    Инструмент, объявленный плагином.

    Уходит в реестр ядра под именем `plugin.<id>.<name>` и получает там
    ровно те же ворота, что встроенный: проверку разрешений, подтверждение
    необратимого, запись в журнал с указанием, какой плагин это затеял.

    `run(args)` вызывается ядром, а не плагином: плагин не решает, когда
    его инструменту работать, — он объявил, что умеет, и ждёт.
    """

    name: str
    summary: str
    run: object = None
    #: Аргументы — теми же `Param`, что у встроенных инструментов.
    params: tuple = ()
    #: Что нужно позволить. Пустой набор — ничего.
    permissions: tuple = ()
    #: Спрашивать человека при каждом вызове.
    confirm_required: bool = False


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
    def page(self):
        """
        Описать свою вкладку списком элементов (см. plugins/page_spec.py).
        Приложение само её нарисует, поэтому плагин не зависит от Qt и
        не сломается при смене оболочки. [] или None — вкладки нет.

        Это рекомендуемый способ (API v2).
        """
        return None

    def on_action(self, action: str, value=None):
        """
        Нажали кнопку с этим action на вкладке плагина.
        После вызова страница пересобирается автоматически.
        """
        pass

    def tools(self):
        """
        Объявить инструменты (API v4).

        Список `PluginTool`. Имена внутри плагина короткие — ядро само
        добавит префикс `plugin.<id>.`, чтобы два плагина с инструментом
        `roll` не спорили за одно имя.

        Разрешения проверяются **до** регистрации: то, что плагину не
        положено (ADR 0010), не выдаётся, а сам инструмент не заводится —
        инструмент без нужного разрешения всё равно отказал бы, но уже
        после того, как человек его увидел и позвал.
        """
        return []

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
