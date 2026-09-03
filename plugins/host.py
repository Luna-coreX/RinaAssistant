# -*- coding: utf-8 -*-
"""
Процесс одного плагина.

Задача плана `4.0-H07`, решение принято ещё в 3.1.0 (ADR 3.1-D01): плагин
перестаёт быть произвольным Python внутри ядра и получает собственный
процесс.

**Почему отдельный процесс, а не try/except.** Ошибку можно поймать;
бесконечный цикл — нельзя. Плагин, ушедший в `while True`, забирает поток
ядра и Рина замолкает целиком; плагин, съевший гигабайт, роняет процесс,
который слушает микрофон. Ловушка исключений от этого не спасает, потому
что исключения тут и нет.

**Тот же провод, что у оболочки.** Конверт, кадрирование, коды ошибок и
трассировка — из `core/wire`: третий формат сообщений в одной программе
означал бы третий разбор, третий набор ошибок и третье место, где они
разъезжаются. Отличается только таблица методов и то, что плагин ничего
не согласовывает: он объявляет себя в ответ на `plugin.hello`, а решает
ядро.

**Направление разговора.** Ядро спрашивает — плагин отвечает. Плагину
разрешено обратиться к ядру ровно за двумя вещами: сказать реплику
(`plugin.respond`) и прочитать или записать свою настройку. Всё остальное
он объявляет инструментами и ждёт, когда ядро их позовёт.

Запуск (ядром, не человеком):
    python -m plugins.host <путь-к-папке-плагина>
"""
import importlib.util
import json
import os
import queue
import sys
import threading
import traceback

# Ядро запускает нас своим интерпретатором из корня проекта, но полагаться
# на это нельзя: путь добавляем сами.
_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from core.trace import NO_TRACE
from core.wire.envelope import (Envelope, FrameDecoder, IdGenerator,
                                MessageType, encode_frame)
from plugins.api import API_VERSION, Plugin, PluginManifest, PluginContext
from plugins.page_spec import page_to_dict


class RemoteContext(PluginContext):
    """
    Контекст плагина, живущего отдельно.

    Плагин зовёт `self.ctx.respond(...)` так же, как раньше; разница в том,
    что вызов уходит по проводу. Обратной связи у настроек нет намеренно:
    ответ на «прочитай настройку» нужен немедленно, поэтому чтение — это
    запрос с ожиданием, а запись — уведомление без него.
    """

    def __init__(self, manifest, host):
        super().__init__(manifest, host)
        self._cache = {}

    def log(self, message):
        self._host.notify_core("plugin.log", {"message": str(message)})

    def respond(self, text):
        self._host.notify_core("plugin.respond", {"text": str(text)})

    def get_setting(self, key, default=None):
        answer = self._host.ask_core("plugin.setting.get", {"key": str(key)})
        if answer is None or "value" not in answer:
            return self._cache.get(key, default)
        value = answer["value"]
        self._cache[key] = value
        return default if value is None else value

    def set_setting(self, key, value):
        self._cache[key] = value
        self._host.notify_core("plugin.setting.set",
                               {"key": str(key), "value": value})

    def notify(self, title, message):
        self._host.notify_core("plugin.notify",
                               {"title": str(title), "message": str(message)})


class Host:
    """Один плагин и провод к ядру."""

    def __init__(self, folder):
        self.folder = folder
        self.plugin = None
        self.manifest = None
        self.error = ""
        self.ids = IdGenerator("p-")
        self.decoder = FrameDecoder()
        self._out = sys.stdout.buffer
        self._lock = threading.Lock()
        self._answers = {}
        self._waiting = {}
        #: Трассировка запроса, который сейчас обрабатываем.
        self._trace = ""
        #: Очередь запросов ядра. Обрабатывает **рабочий** поток: страница
        #: плагина может по дороге спросить настройку, а ответ на этот
        #: вопрос принесёт приёмный поток. Обрабатывай мы запросы прямо в
        #: нём — плагин ждал бы ответа тем потоком, который его принесёт,
        #: и не дождался бы никогда. Так и вышло при первом запуске.
        self._work = queue.Queue()

    # -- провод --------------------------------------------------------------
    def send(self, envelope):
        with self._lock:
            self._out.write(encode_frame(envelope))
            self._out.flush()

    def notify_core(self, method, payload):
        """
        Сказать ядру и не ждать: у реплики нет ответа.

        Трассировка — та, под которой нас позвали: реплика плагина
        рождается внутри обработки команды, и терять на ней цепочку
        значило бы иметь в журнале ответ без вопроса.
        """
        self.send(Envelope.event(method, dict(payload), id=self.ids.next(),
                                 trace_id=self._trace or NO_TRACE))

    def ask_core(self, method, payload, timeout=5.0):
        """
        Спросить ядро и дождаться.

        Ждёт **рабочий** поток, а не приёмный: ответ принесёт приёмный, и
        заблокировать его значило бы ждать самого себя. Здесь плагин
        однопоточен, поэтому ожидание простое, но правило то же, что в
        ядре (`ask_shell_sync`).
        """
        request = Envelope.request(method, dict(payload), id=self.ids.next(),
                                   trace_id=self._trace or NO_TRACE)
        done = threading.Event()
        self._waiting[request.id] = done
        self.send(request)
        if not done.wait(timeout):
            self._waiting.pop(request.id, None)
            return None
        return self._answers.pop(request.id, None)

    # -- загрузка ------------------------------------------------------------
    def load(self):
        path = os.path.join(self.folder, "plugin.json")
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as exc:                         # noqa: BLE001
            self.error = f"Ошибка манифеста: {exc}"
            return False

        self.manifest = PluginManifest.from_dict(data, path=self.folder)
        self.manifest.id = os.path.basename(self.folder)
        if not self.manifest.api_compatible():
            self.error = self.manifest.why_incompatible()
            return False

        main = os.path.join(self.folder, "main.py")
        if not os.path.isfile(main):
            self.error = "Нет файла main.py"
            return False

        try:
            spec = importlib.util.spec_from_file_location(
                f"rina_plugin_{self.manifest.id}", main)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except Exception:                                # noqa: BLE001
            self.error = "Ошибка загрузки:\n" + traceback.format_exc(limit=3)
            return False

        found = None
        if self.manifest.entry:
            found = getattr(module, self.manifest.entry, None)
        if found is None:
            for value in vars(module).values():
                if (isinstance(value, type) and issubclass(value, Plugin)
                        and value is not Plugin):
                    found = value
                    break
        if found is None:
            self.error = "В main.py нет класса-наследника Plugin"
            return False

        try:
            self.plugin = found(RemoteContext(self.manifest, self))
        except Exception:                                # noqa: BLE001
            self.error = "Ошибка создания:\n" + traceback.format_exc(limit=3)
            return False
        return True

    # -- методы, которые зовёт ядро -----------------------------------------
    def accept(self, message):
        """
        Разобрать пришедшее: ответ — сразу, запрос — в очередь.

        Приёмный поток обязан остаться свободным: он единственный, кто
        может принести ответ на вопрос плагина.
        """
        if message.type == MessageType.RESPONSE:
            done = self._waiting.pop(message.correlation_id, None)
            if done is not None:
                self._answers[message.correlation_id] = dict(message.payload)
                done.set()
            return
        if message.type == MessageType.REQUEST:
            self._work.put(message)

    def work_forever(self):
        """Один рабочий поток: состояние плагина не потокобезопасно."""
        while True:
            message = self._work.get()
            if message is None:
                return
            self.handle(message)
            if message.method == "plugin.shutdown":
                return

    def handle(self, message):
        self._trace = message.trace_id
        try:
            payload = self._serve(message.method, message.payload)
        except Exception:                                # noqa: BLE001
            # Плагин уронил обработчик. Отвечаем ошибкой: молчание
            # превратится в таймаут у ядра, а таймаут — в «плагин зависли»,
            # хотя он всего лишь ошибся.
            from core.wire.errors import make

            self.send(message.fail(
                make("internal", traceback.format_exc(limit=3)),
                id=self.ids.next()))
            return
        self.send(message.reply(payload, id=self.ids.next()))

    def _serve(self, method, payload):
        if method == "plugin.hello":
            return {
                "api_version": API_VERSION,
                "ok": self.plugin is not None,
                "error": self.error,
                "manifest": {
                    "id": self.manifest.id if self.manifest else "",
                    "name": self.manifest.name if self.manifest else "",
                    "version": self.manifest.version if self.manifest else "",
                    "author": self.manifest.author if self.manifest else "",
                    "description": (self.manifest.description
                                    if self.manifest else ""),
                    "icon": self.manifest.icon if self.manifest else "🧩",
                    "permissions": list(self.manifest.permissions
                                        if self.manifest else ()),
                },
                "has_page": (self.plugin is not None
                             and type(self.plugin).page is not Plugin.page),
                "tools": self._tools(),
            }

        if self.plugin is None:
            return {"ok": False, "error": self.error}

        if method == "plugin.enable":
            self.plugin.on_enable()
            return {"ok": True}
        if method == "plugin.disable":
            self.plugin.on_disable()
            return {"ok": True}
        if method == "plugin.command":
            handled = bool(self.plugin.on_command(
                str(payload.get("text", ""))))
            return {"handled": handled}
        if method == "plugin.event":
            self.plugin.on_event(str(payload.get("name", "")),
                                 payload.get("data") or {})
            return {"ok": True}
        if method == "plugin.page":
            return {"elements": page_to_dict(self.plugin.page() or [])}
        if method == "plugin.action":
            self.plugin.on_action(str(payload.get("action", "")),
                                  payload.get("value"))
            return {"elements": page_to_dict(self.plugin.page() or [])}
        if method == "plugin.call":
            return self._call(payload)
        if method == "plugin.shutdown":
            return {"ok": True}

        return {"ok": False, "error": f"неизвестный метод: {method}"}

    def _tools(self):
        """Объявленные инструменты — описанием, без вызываемых объектов."""
        if self.plugin is None:
            return []
        listed = []
        for one in (self.plugin.tools() or []):
            listed.append({
                "name": str(one.name),
                "summary": str(one.summary),
                "permissions": [str(p) for p in (one.permissions or ())],
                "confirm_required": bool(one.confirm_required),
                "params": [p.to_dict() for p in (one.params or ())],
            })
        return listed

    def _call(self, payload):
        name = str(payload.get("name", ""))
        args = payload.get("args") or {}
        for one in (self.plugin.tools() or []):
            if str(one.name) != name or one.run is None:
                continue
            answer = one.run(args)
            return {"ok": True, "value": answer if answer is None
                    else str(answer)}
        return {"ok": False, "error": f"нет инструмента: {name}"}

    # -- цикл ----------------------------------------------------------------
    def serve_forever(self):
        source = sys.stdin.buffer
        while True:
            header = source.read(4)
            if not header or len(header) < 4:
                return
            size = int.from_bytes(header, "big")
            body = b""
            while len(body) < size:
                piece = source.read(size - len(body))
                if not piece:
                    return
                body += piece
            for message in self.decoder.feed(header + body):
                self.accept(message)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print("нужно: путь-к-папке-плагина", file=sys.stderr)
        return 2

    # Плагин не должен писать в стандартный вывод: там наш провод. Своё
    # `print` в плагине иначе испортил бы кадр посреди сообщения.
    host = Host(argv[0])
    real_stdout = sys.stdout
    sys.stdout = sys.stderr
    try:
        host.load()
        worker = threading.Thread(target=host.work_forever, daemon=True)
        worker.start()
        host.serve_forever()
        # Провод кончился — ядро ушло. Рабочему потоку тоже пора.
        host._work.put(None)
        worker.join(timeout=2.0)
    finally:
        sys.stdout = real_stdout
    return 0


if __name__ == "__main__":
    sys.exit(main())
