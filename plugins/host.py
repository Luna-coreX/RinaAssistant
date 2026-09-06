# -*- coding: utf-8 -*-
"""
One plugin's process.

Plan item `4.0-H07`; the decision was taken back in 3.1.0 (ADR 3.1-D01): a
plugin stops being arbitrary Python inside the core and gets a process of
its own.

**Why a separate process rather than try/except.** An error can be caught;
an infinite loop cannot. A plugin that has gone into a `while True` takes
the core's thread and Rina falls silent entirely; a plugin that ate a
gigabyte drops the process that listens to the microphone. An exception trap
does not save one from that, because there is no exception here.

**The same wire as the shell's.** The envelope, the framing, the error codes
and the tracing come from `core/wire`: a third message format in one program
would mean a third parser, a third set of errors and a third place where
they drift apart. What differs is only the method table and the fact that a
plugin negotiates nothing: it declares itself in answer to `plugin.hello`,
and the core decides.

**The direction of the conversation.** The core asks, the plugin answers. A
plugin is allowed to turn to the core for exactly two things: to say a line
(`plugin.respond`) and to read or write a setting of its own. Everything
else it declares as tools and waits for the core to call them.

Started (by the core, not by a person):
    python -m plugins.host <path-to-the-plugin-folder>
"""
import importlib.util
import json
import os
import queue
import sys
import threading
import traceback

# The core starts us with its own interpreter from the project root, but
# that must not be relied on: we add the path ourselves.
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
    The context of a plugin living separately.

    A plugin calls `self.ctx.respond(...)` just as before; the difference is
    that the call goes over the wire. Settings deliberately have no
    round-trip: the answer to "read the setting" is needed immediately, so
    reading is a request with a wait, and writing is a notification without
    one.
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
    """One plugin and the wire to the core."""

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
        #: The trace of the request being handled right now.
        self._trace = ""
        #: The queue of the core's requests. The **worker** thread handles
        #: it: a plugin's page may ask for a setting along the way, and the
        #: answer to that question will be brought by the receiving thread.
        #: Were we to handle requests in that thread, the plugin would wait
        #: for the answer with the very thread that will bring it, and would
        #: wait forever. Which is what happened on the first run.
        self._work = queue.Queue()

    # -- the wire ---------------------------------------------------------------
    def send(self, envelope):
        with self._lock:
            self._out.write(encode_frame(envelope))
            self._out.flush()

    def notify_core(self, method, payload):
        """
        Tell the core and do not wait: a line has no answer.

        The trace is the one we were called under: a plugin's line is born
        inside the handling of a command, and losing the chain on it would
        mean having an answer without a question in the journal.
        """
        self.send(Envelope.event(method, dict(payload), id=self.ids.next(),
                                 trace_id=self._trace or NO_TRACE))

    def ask_core(self, method, payload, timeout=5.0):
        """
        Ask the core and wait.

        The **worker** thread waits, not the receiving one: the receiving
        thread will bring the answer, and blocking it would mean waiting for
        oneself. The plugin here is single-threaded, so the waiting is
        simple, but the rule is the same as in the core (`ask_shell_sync`).
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

    # -- loading ------------------------------------------------------------------
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

    # -- the methods the core calls -------------------------------------------
    def accept(self, message):
        """
        Parse what arrived: an answer at once, a request into the queue.

        The receiving thread is obliged to stay free: it is the only one
        that can bring the answer to the plugin's question.
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
        """One worker thread: a plugin's state is not thread-safe."""
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
            # The plugin dropped the handler. We answer with an error:
            # silence would turn into a timeout at the core, and a timeout
            # into "the plugin has hung", when all it did was make a
            # mistake.
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
                # What to call the plugin's section in the column. A plugin
                # is entitled to call itself something other than its name
                # in the installed list: "Notes" is shorter than "Quick
                # notes", and room in the column is dear.
                "page_title": str(getattr(self.plugin, "page_title", "")
                                  or (self.manifest.name if self.manifest
                                      else "")),
                "page_icon": str(getattr(self.plugin, "page_icon", "")
                                 or (self.manifest.icon if self.manifest
                                     else "🧩")),
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
        """The declared tools — as descriptions, without callables."""
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

    # -- the loop ------------------------------------------------------------------
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

    # A plugin must not write to standard output: our wire is there. A
    # `print` of its own inside a plugin would otherwise spoil a frame in
    # the middle of a message.
    host = Host(argv[0])
    real_stdout = sys.stdout
    sys.stdout = sys.stderr
    try:
        host.load()
        worker = threading.Thread(target=host.work_forever, daemon=True)
        worker.start()
        host.serve_forever()
        # The wire has ended — the core is gone. It is time for the worker thread too.
        host._work.put(None)
        worker.join(timeout=2.0)
    finally:
        sys.stdout = real_stdout
    return 0


if __name__ == "__main__":
    sys.exit(main())
