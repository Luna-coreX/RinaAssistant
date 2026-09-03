# -*- coding: utf-8 -*-
"""
Плагины, живущие отдельными процессами.

Задача плана `4.0-H07`. Наружу отдаётся **та же поверхность**, что у
`plugins.manager.PluginManager`: `discover`, `enable`, `disable`,
`dispatch_command`, `page_plugins`, `get_plugin_page_spec`,
`dispatch_action`, `declared_tools`, сигналы. Ядро и сервер протокола не
знают, где живёт плагин, — и не должны: подмена одного менеджера другим не
имеет права быть заметной.

**Что даёт процесс.** Плагин, ушедший в бесконечный цикл, не забирает
поток ядра: ответа нет, срок истекает, плагин помечается сбойным и
убивается. Плагин, упавший с исключением, роняет себя. Ассистент при этом
продолжает работать — это и есть критерий приёмки задачи.

**Срок ответа, а не бесконечное ожидание.** Каждый вызов ограничен по
времени. Без срока «плагин задумался» и «плагин повесился» — одно и то же
состояние, и различить их нечем.

**Один процесс на плагин, а не один на всех.** Иначе один сбойный плагин
уносил бы с собой соседей, и мы бы вернулись к тому, от чего ушли, — просто
на процесс дальше.
"""
import os
import subprocess
import sys
import threading
import time

from core.logging_setup import get_logger
from core.trace import NO_TRACE, current_trace
from core.wire.envelope import (Envelope, FrameDecoder, IdGenerator,
                                MessageType, encode_frame)

log = get_logger("plugins")

#: Сколько ждать ответа на обычный вызов.
CALL_TIMEOUT = 10.0

#: Сколько ждать, пока процесс поднимется и представится.
START_TIMEOUT = 20.0

#: Сколько ждать, пока убитый процесс действительно уйдёт.
KILL_TIMEOUT = 5.0


class Signal:
    """
    Оповещение подписчиков — то же, что в `plugins.manager`.

    Своё, а не оттуда: этот модуль не должен зависеть от менеджера,
    которого он заменяет.
    """

    def __init__(self, *types):
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
        for listener in list(self._listeners):
            try:
                listener(*args)
            except Exception:                            # noqa: BLE001
                log.exception("Подписчик сигнала уронил обработчик")


class Manifest:
    """Что плагин рассказал о себе. Обёртка ради той же поверхности."""

    def __init__(self, data=None, folder=""):
        data = data or {}
        self.id = str(data.get("id", "") or os.path.basename(folder))
        self.name = str(data.get("name", self.id))
        self.version = str(data.get("version", "1.0.0"))
        self.author = str(data.get("author", "unknown"))
        self.description = str(data.get("description", ""))
        self.icon = str(data.get("icon", "🧩"))
        self.path = folder
        self.api_version = int(data.get("api_version", 0) or 0)
        self.permissions = tuple(data.get("permissions") or ())


class HostedPlugin:
    """Один плагин и процесс, в котором он живёт."""

    def __init__(self, folder, owner):
        self.folder = folder
        self.manifest = Manifest(folder=folder)
        self.instance = None        # для совместимости поверхности
        self.enabled = False
        self.error = None
        self.logs = []
        self.has_page = False
        self.tools = []

        self._owner = owner
        self._proc = None
        self._ids = IdGenerator(f"h-{os.path.basename(folder)}-")
        self._decoder = FrameDecoder()
        self._lock = threading.Lock()
        self._pending = {}
        self._reader = None

    # -- жизнь процесса ------------------------------------------------------
    @property
    def alive(self):
        return self._proc is not None and self._proc.poll() is None

    def start(self):
        """Поднять процесс и дождаться, пока плагин представится."""
        if self.alive:
            return True

        launcher = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "plugins", "host.py")
        try:
            self._proc = subprocess.Popen(
                [sys.executable, "-u", launcher, self.folder],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=os.path.dirname(launcher))
        except Exception as exc:                         # noqa: BLE001
            self.error = f"Плагин не запустился: {exc}"
            return False

        self._decoder = FrameDecoder()
        self._reader = threading.Thread(target=self._read_forever, daemon=True)
        self._reader.start()

        answer = self.ask("plugin.hello", {}, timeout=START_TIMEOUT)
        if answer is None:
            self.error = "Плагин не ответил на приветствие."
            self.kill()
            return False

        self.manifest = Manifest(answer.get("manifest") or {}, self.folder)
        self.manifest.api_version = int(answer.get("api_version", 0) or 0)
        self.has_page = bool(answer.get("has_page"))
        self.tools = list(answer.get("tools") or [])

        if not answer.get("ok"):
            # Плагин поднялся, но собой быть не смог: старый API, битый
            # main.py. Причину он уже назвал — её и показываем.
            self.error = str(answer.get("error") or "Плагин не загрузился.")
            self.kill()
            return False

        self.error = None
        return True

    def kill(self):
        """Убить процесс. Мягко не просим: спрашивали уже."""
        proc, self._proc = self._proc, None
        if proc is None:
            return
        try:
            proc.kill()
            proc.wait(timeout=KILL_TIMEOUT)
        except Exception:                                # noqa: BLE001
            pass
        with self._lock:
            for done in self._pending.values():
                done.set()
            self._pending.clear()

    def stop(self):
        """Попросить закрыться, потом убить."""
        if self.alive:
            self.ask("plugin.shutdown", {}, timeout=2.0)
        self.kill()

    # -- разговор ------------------------------------------------------------
    def ask(self, method, payload=None, timeout=CALL_TIMEOUT):
        """
        Спросить плагин и дождаться ответа. `None` — не ответил.

        Срок обязателен: без него «плагин задумался» и «плагин повесился» —
        одно и то же состояние. Не ответивший в срок считается сбойным и
        убивается: процесс, который не отвечает, уже ничем не полезен, а
        память и процессор занимает.
        """
        if not self.alive:
            return None

        request = Envelope.request(
            method, dict(payload or {}), id=self._ids.next(),
            trace_id=current_trace() or NO_TRACE)
        done = threading.Event()
        holder = {}
        with self._lock:
            self._pending[request.id] = done
            self._answers = getattr(self, "_answers", {})
            self._answers[request.id] = holder

        try:
            self._proc.stdin.write(encode_frame(request))
            self._proc.stdin.flush()
        except Exception:                                # noqa: BLE001
            self._forget(request.id)
            self.error = "Плагин оборвал связь."
            self.kill()
            return None

        if not done.wait(timeout):
            self._forget(request.id)
            self.error = (f"Плагин не ответил за {timeout:.0f} с "
                          f"и был остановлен.")
            log.warning("Плагин «%s» не ответил на %s", self.manifest.id,
                        method)
            self.kill()
            self.enabled = False
            self._owner.changed.emit()
            return None

        # Разбудить могли и обрывом связи, а не ответом.
        if not holder and not self.alive:
            self._forget(request.id)
            self.error = self.error or "Плагин упал."
            self.enabled = False
            return None

        answer = holder.get("payload")
        self._forget(request.id)
        if holder.get("error"):
            self.error = str(holder["error"])
            return None
        return answer

    def _forget(self, request_id):
        with self._lock:
            self._pending.pop(request_id, None)
            getattr(self, "_answers", {}).pop(request_id, None)

    def _read_forever(self):
        """Читать ответы и просьбы плагина, пока процесс жив."""
        proc = self._proc
        source = proc.stdout if proc else None
        while source is not None:
            header = source.read(4)
            if not header or len(header) < 4:
                break
            size = int.from_bytes(header, "big")
            body = b""
            while len(body) < size:
                piece = source.read(size - len(body))
                if not piece:
                    break
                body += piece
            for message in self._decoder.feed(header + body):
                self._on_message(message)

        # Провод кончился — процесса больше нет. Ждущих надо отпустить
        # немедленно: иначе «плагин упал» станет известно только по
        # истечении срока, то есть через десять секунд после того, как это
        # уже произошло.
        with self._lock:
            for done in self._pending.values():
                done.set()

        # Если процесс не убивали мы, это падение.
        if self._proc is proc and proc is not None and proc.poll() not in (
                None, 0):
            self.error = "Плагин упал."
            self.enabled = False
            log.warning("Плагин «%s» упал (код %s)", self.manifest.id,
                        proc.poll())
            self._owner.changed.emit()

    def _on_message(self, message):
        if message.type in (MessageType.RESPONSE, MessageType.ERROR):
            with self._lock:
                holder = getattr(self, "_answers", {}).get(
                    message.correlation_id)
                done = self._pending.get(message.correlation_id)
            if holder is not None:
                if message.type == MessageType.ERROR:
                    holder["error"] = message.payload.get("message", "")
                else:
                    holder["payload"] = dict(message.payload)
            if done is not None:
                done.set()
            return

        # Просьбы плагина: их ровно три, и ни одна не про мир снаружи.
        self._owner.serve_plugin(self, message)


class HostedPlugins:
    """
    Все плагины, каждый в своём процессе.

    Поверхность повторяет `PluginManager` нарочно: ядро не должно знать,
    где живёт плагин.
    """

    def __init__(self, settings=None):
        self.plugins = {}
        self.changed = Signal()
        self.log_added = Signal(str, str)
        self.response = Signal(str, str)
        self.pages_changed = Signal()
        self.notify_requested = Signal(str, str, str)
        #: Настройки плагинов хранит ядро: плагин пишет своё, а где это
        #: лежит — не его дело. Заодно так его настройки переживают его
        #: собственное падение.
        self._settings = settings

    # -- обнаружение ---------------------------------------------------------
    def discover(self):
        """
        Найти папки плагинов. Кода при этом **не запускаем**.

        Процесс поднимается при включении, а не при обнаружении: иначе
        сбойный плагин мешал бы уже старту Рины, а список плагинов
        стоил бы столько же, сколько их запуск.
        """
        from plugins.manager import plugins_dir

        base = plugins_dir()
        known = set()
        enabled = set()
        if self._settings is not None:
            enabled = set(self._settings.get("enabled_plugins", []) or [])

        for name in sorted(os.listdir(base)):
            folder = os.path.join(base, name)
            if not os.path.isdir(folder):
                continue
            if not os.path.isfile(os.path.join(folder, "plugin.json")):
                continue
            known.add(name)
            if name not in self.plugins:
                self.plugins[name] = HostedPlugin(folder, self)
                self._read_manifest(self.plugins[name])

        for gone in set(self.plugins) - known:
            self.plugins.pop(gone).stop()

        for plugin_id in sorted(enabled & known):
            self.enable(plugin_id, persist=False)

        log.info("Плагинов найдено: %d", len(self.plugins))
        self.changed.emit()
        return self.plugins

    @staticmethod
    def _read_manifest(hosted):
        """
        Прочитать манифест, не запуская плагин.

        Список плагинов должен быть виден до того, как их включат: человек
        выбирает из имён и описаний, а не из работающих процессов.
        """
        import json

        try:
            with open(os.path.join(hosted.folder, "plugin.json"),
                      encoding="utf-8") as f:
                hosted.manifest = Manifest(json.load(f), hosted.folder)
        except Exception as exc:                         # noqa: BLE001
            hosted.error = f"Ошибка манифеста: {exc}"

    # -- включение -----------------------------------------------------------
    def enable(self, plugin_id, persist=True):
        hosted = self.plugins.get(plugin_id)
        if hosted is None:
            return False
        if hosted.enabled and hosted.alive:
            return True

        if not hosted.start():
            self.changed.emit()
            return False

        hosted.ask("plugin.enable", {})
        hosted.enabled = True
        if persist:
            self._persist()
        self.changed.emit()
        self.pages_changed.emit()
        return True

    def disable(self, plugin_id, persist=True):
        hosted = self.plugins.get(plugin_id)
        if hosted is None:
            return False
        if hosted.alive:
            hosted.ask("plugin.disable", {}, timeout=3.0)
        hosted.stop()
        hosted.enabled = False
        if persist:
            self._persist()
        self.changed.emit()
        self.pages_changed.emit()
        return True

    def toggle(self, plugin_id, on):
        return self.enable(plugin_id) if on else self.disable(plugin_id)

    def _persist(self):
        if self._settings is None:
            return
        with self._settings.transaction():
            self._settings.set("enabled_plugins",
                               sorted(pid for pid, p in self.plugins.items()
                                      if p.enabled))
            self._settings.save()

    def stop_all(self):
        for hosted in self.plugins.values():
            hosted.stop()

    # -- то, чем пользуется ядро --------------------------------------------
    def dispatch_command(self, text):
        """
        Отдать команду плагинам. `True` — кто-то взял.

        Порядок стабильный: два плагина, откликающиеся на одно слово, иначе
        отвечали бы по-разному от запуска к запуску.
        """
        for plugin_id in sorted(self.plugins):
            hosted = self.plugins[plugin_id]
            if not hosted.enabled or not hosted.alive:
                continue
            answer = hosted.ask("plugin.command", {"text": str(text)})
            if answer and answer.get("handled"):
                return True
        return False

    def broadcast_event(self, name, data=None):
        for hosted in self.plugins.values():
            if hosted.enabled and hosted.alive:
                hosted.ask("plugin.event",
                           {"name": str(name), "data": data or {}},
                           timeout=3.0)

    def page_plugins(self):
        return [(pid, self.plugins[pid]) for pid in sorted(self.plugins)
                if self.plugins[pid].enabled and self.plugins[pid].has_page]

    def get_plugin_page_spec(self, plugin_id):
        hosted = self.plugins.get(plugin_id)
        if hosted is None or not hosted.alive:
            return []
        answer = hosted.ask("plugin.page", {})
        return _as_elements((answer or {}).get("elements") or [])

    def dispatch_action(self, plugin_id, action, value=None):
        hosted = self.plugins.get(plugin_id)
        if hosted is None or not hosted.alive:
            return
        hosted.ask("plugin.action", {"action": str(action), "value": value})

    def tool_prefix(self, plugin_id):
        return f"plugin.{plugin_id}."

    def declared_tools(self, plugin_id):
        """
        Инструменты плагина — с проверенными разрешениями (ADR 0010).

        Описание пришло из процесса плагина; `Tool` строится **здесь**,
        потому что проверять разрешения имеет право только эта сторона.
        Плагин может объявить что угодно; заводится то, что позволено.
        """
        from core.permissions import plugin_allowed
        from core.tools import Param, Tool

        hosted = self.plugins.get(plugin_id)
        if hosted is None or not hosted.enabled:
            return []

        allowed, refused = plugin_allowed(hosted.manifest.permissions)
        if refused:
            self._note(plugin_id, "Не выдано разрешений: " + ", ".join(refused))

        made = []
        for one in hosted.tools:
            wanted = {str(p) for p in (one.get("permissions") or ())}
            if not wanted.issubset(set(allowed)):
                self._note(plugin_id,
                           f"Инструмент «{one.get('name')}» не заведён: "
                           f"просит {sorted(wanted - set(allowed))}")
                continue
            try:
                params = tuple(
                    Param(name=str(p.get("name", "")),
                          type=str(p.get("type", "string")),
                          description=str(p.get("description", "")),
                          required=bool(p.get("required", True)),
                          choices=tuple(p.get("choices") or ()),
                          minimum=p.get("minimum"),
                          maximum=p.get("maximum"))
                    for p in (one.get("params") or ()))
                tool = Tool(
                    name=self.tool_prefix(plugin_id) + str(one.get("name", "")),
                    summary=str(one.get("summary", "")),
                    params=params,
                    permissions=frozenset(wanted),
                    confirm_required=bool(one.get("confirm_required")),
                )
            except Exception as exc:                     # noqa: BLE001
                self._note(plugin_id, f"Инструмент отклонён: {exc}")
                continue
            made.append((tool, self._caller(plugin_id, str(one.get("name")))))
        return made

    def _caller(self, plugin_id, name):
        from core.toolrunner import ToolResult

        def run(ctx, args):
            hosted = self.plugins.get(plugin_id)
            if hosted is None or not hosted.alive:
                return ToolResult.failed("Плагин не запущен.", "internal")
            answer = hosted.ask("plugin.call", {"name": name, "args": args})
            if answer is None:
                return ToolResult.failed("Плагин не ответил.", "internal")
            if not answer.get("ok"):
                return ToolResult.failed(
                    str(answer.get("error") or "Плагин не справился."),
                    "internal")
            return ToolResult.done(str(answer.get("value") or ""))

        return run

    # -- просьбы плагина -----------------------------------------------------
    def serve_plugin(self, hosted, message):
        """
        Ответить плагину. Просьб ровно три, и ни одна не про мир снаружи.

        Плагин не может ни запустить программу, ни открыть окно, ни узнать
        о соседях: всё, что он умеет делать с миром, объявлено
        инструментами и проходит через реестр (ADR 0010).
        """
        plugin_id = hosted.manifest.id
        method = message.method

        if method == "plugin.respond":
            self.response.emit(plugin_id, str(message.payload.get("text", "")))
        elif method == "plugin.log":
            self._note(plugin_id, str(message.payload.get("message", "")))
        elif method == "plugin.notify":
            self.notify_requested.emit(
                plugin_id, str(message.payload.get("title", "")),
                str(message.payload.get("message", "")))
        elif method == "plugin.setting.get":
            value = self._setting(plugin_id, str(message.payload.get("key")))
            self._answer(hosted, message, {"value": value})
            return
        elif method == "plugin.setting.set":
            self._set_setting(plugin_id, str(message.payload.get("key")),
                              message.payload.get("value"))
        else:
            # Метод, которого мы не знаем, — не повод молчать: плагин ждёт.
            self._answer(hosted, message,
                         {"ok": False, "error": "неизвестный метод"})
            return

        if message.type == MessageType.REQUEST:
            self._answer(hosted, message, {"ok": True})

    @staticmethod
    def _answer(hosted, message, payload):
        if message.type != MessageType.REQUEST or not hosted.alive:
            return
        try:
            hosted._proc.stdin.write(
                encode_frame(message.reply(payload, id=hosted._ids.next())))
            hosted._proc.stdin.flush()
        except Exception:                                # noqa: BLE001
            hosted.kill()

    def _note(self, plugin_id, message):
        hosted = self.plugins.get(plugin_id)
        if hosted is not None:
            hosted.logs.append(message)
            del hosted.logs[:-100]
        log.info("[%s] %s", plugin_id, message)
        self.log_added.emit(plugin_id, message)

    # -- настройки плагина ---------------------------------------------------
    def _bag(self):
        if self._settings is None:
            return {}
        return dict(self._settings.get("plugin_settings", {}) or {})

    def _setting(self, plugin_id, key, default=None):
        return self._bag().get(plugin_id, {}).get(key, default)

    def _set_setting(self, plugin_id, key, value):
        if self._settings is None:
            return
        with self._settings.transaction():
            bag = self._bag()
            bag.setdefault(plugin_id, {})[key] = value
            self._settings.set("plugin_settings", bag)
            self._settings.save()

    # Совместимость поверхности: менеджер в процессе умеет и это.
    def get_plugin_setting(self, plugin_id, key, default=None):
        return self._setting(plugin_id, key, default)

    def set_plugin_setting(self, plugin_id, key, value):
        self._set_setting(plugin_id, key, value)


class _Element:
    """Элемент страницы, пришедший от плагина, — в виде объекта."""

    __slots__ = ("kind", "data")

    def __init__(self, data):
        self.kind = str(data.get("kind", ""))
        self.data = dict(data)

    def to_dict(self):
        return dict(self.data)


def _as_elements(listed):
    """
    Обернуть словари в объекты с `to_dict` и `kind`.

    Нужно ради той же поверхности: сервер протокола зовёт `to_dict()` у
    элементов, и ему не должно быть важно, пришли они из процесса рядом
    или собрались здесь.
    """
    return [_Element(item) for item in listed if isinstance(item, dict)]
