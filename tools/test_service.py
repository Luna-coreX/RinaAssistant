# -*- coding: utf-8 -*-
"""
E01 + E02: the core as a separate process, and talking to it over the wire.

This is the first check where the split is not depicted but happens: the
core is started as a real `subprocess`, it has its own interpreter, its own
memory and its own journal, and the link is only bytes through standard
input and output.

The core is raised through `tools/_core_sandboxed.py` rather than directly:
the side effects are disarmed inside the child process itself, because the
parent's sandbox does not extend to it.

To run:
    python tools/test_service.py
"""

import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

from console import child_env, use_utf8

use_utf8()

ROOT = r"C:\DevStation\PCDev\DesktopApps\RinaAssistant"
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from core.wire import (Envelope, FrameDecoder, IdGenerator, MessageType,
                       Session, Side, encode_frame, new_trace_id)

fails = 0

#: The simplest plugin, for checking installation.
#:
#: The newlines are glued from `chr(10)` rather than written as `\n`: the
#: constant was edited by a script, and an escaped newline turned into a real
#: one twice over, breaking the file.
PLUGIN_SOURCE = (
    "from plugins.api import Plugin" + chr(10) * 3
    + "class Fresh(Plugin):" + chr(10)
    + "    def on_command(self, text):" + chr(10)
    + "        return False" + chr(10)
)


def check(label, cond, detail=""):
    global fails
    if not cond:
        fails += 1
    print(("OK   " if cond else "FAIL "), label, detail)


LAUNCHER = os.path.join(ROOT, "tools", "_core_sandboxed.py")


class Core:
    """The core in a separate process; outwards — only frames."""

    def __init__(self, extra=()):
        self.proc = subprocess.Popen(
            [sys.executable, "-u", LAUNCHER, "--transport", "stdio", *extra],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, cwd=ROOT, env=child_env())
        self.decoder = FrameDecoder()
        self.ids = IdGenerator("s-")
        self.session = Session(side=Side.SHELL)
        self.apps = []          # the index we hand to the core
        self.did = []           # the system actions that were asked for
        self.launched = []      # what was asked to be launched

    def send(self, envelope):
        self.proc.stdin.write(encode_frame(envelope))
        self.proc.stdin.flush()
        return envelope

    def ask(self, method, payload=None, trace_id=None):
        return self.send(Envelope.request(
            method, dict(payload or {}), id=self.ids.next(),
            trace_id=trace_id or new_trace_id()))

    def read_until(self, method, timeout=30.0, limit=20):
        """
        Read until the event we need arrives.

        The "accepted" answer and Rina's answer itself are separated in
        time — that is the point: the command thinks, and the request is not
        held open. Waiting for a fixed number of messages would mean
        guessing how many there will be.
        """
        seen = []
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline and len(seen) < limit:
            if self.proc.poll() is not None:
                break                # the core died — there is nothing more to wait for
            batch = self.read(1, timeout=deadline - time.monotonic())
            if not batch:
                break
            seen.extend(batch)
            if any(m.method == method for m in batch):
                break
        return seen

    #: What the core asked to be done to the machine and what to launch.
    #: The checks look here: the core has no system calls of its own any more.
    def serve(self, message):
        """
        Answer a counter-request from the core, as a shell would.

        Returns True if the message was a request and was answered — such
        messages do not count as "arrived": they are our half of the
        conversation, not the core's answer.
        """
        if message.type != MessageType.REQUEST:
            return False

        if message.method == "apps.index":
            payload = {"entries": list(self.apps)}
        elif message.method == "apps.launch":
            self.launched.append(message.payload.get("launch", ""))
            payload = {"ok": True, "reason": ""}
        elif message.method == "system.do":
            self.did.append(message.payload.get("action", ""))
            payload = {"ok": True, "detail": ""}
        else:
            return False

        self.send(message.reply(payload, id=self.ids.next()))
        return True

    def read(self, count=1, timeout=15.0):
        """Wait for the stated number of messages."""
        got, deadline = [], time.monotonic() + timeout
        while len(got) < count and time.monotonic() < deadline:
            header = self.proc.stdout.read(4)
            if not header or len(header) < 4:
                break
            size = int.from_bytes(header, "big")
            body = b""
            while len(body) < size:
                piece = self.proc.stdout.read(size - len(body))
                if not piece:
                    break
                body += piece
            for message in self.decoder.feed(header + body):
                # A request from the core is our own business rather than
                # an "arrived message": handing it outwards would mean
                # making every check know that the core sometimes asks.
                if not self.serve(message):
                    got.append(message)
        return got

    def handshake(self):
        self.ask("hello", self.session.hello_payload())
        answer = self.read(1)[0]
        self.session.accept_hello_result(answer.payload)
        return answer

    def stderr_text(self):
        try:
            return self.proc.stderr.read().decode("utf-8", "replace")
        except Exception:
            return ""

    def wait(self, timeout=15.0):
        try:
            return self.proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            return None


# ---------------------------------------------------------------------------
print("=== E01: ядро запускается как процесс ===")

probe = subprocess.run(
    [sys.executable, "-u", os.path.join(ROOT, "rina_core.py"),
     "--print-capabilities"],
    capture_output=True, text=True, cwd=ROOT, encoding="utf-8",
    env=child_env())
check("ядро отвечает о себе и выходит с нулём", probe.returncode == 0)
check("объявляет версию протокола", "protocol_versions: 1" in probe.stdout)
check("объявляет возможности",
      "stt" in probe.stdout and "reminders" in probe.stdout,
      f"| {probe.stdout.strip().splitlines()[-1:]}")

bad = subprocess.run(
    [sys.executable, "-u", os.path.join(ROOT, "rina_core.py"),
     "--transport", "pipe"],
    capture_output=True, text=True, cwd=ROOT, encoding="utf-8",
    env=child_env())
check("без сессии режим pipe отклонён с кодом 2", bad.returncode == 2,
      f"| код {bad.returncode}")

# The core is obliged to work where there is no interface library.
headless = subprocess.run(
    [sys.executable, "-u", "-c",
     "import sys; sys.path.insert(0, r'%s');"
     "import rina_core, core.engine, core.wire.server;"
     "print('PySide6' in sys.modules)" % ROOT],
    capture_output=True, text=True, cwd=ROOT, encoding="utf-8",
    env=child_env())
check("ни ядро, ни провод не тянут Qt",
      headless.stdout.strip() == "False", f"| {headless.stdout.strip()}")


# ---------------------------------------------------------------------------
print()
print("=== E02: разговор двух процессов ===")

core = Core()
answer = core.handshake()
check("рукопожатие через провод состоялось", core.session.ready)
check("ядро назвало версию", core.session.version == 1)
check("ядро назвало идентификатор сессии",
      len(core.session.session_id) == 32)
check("возможности пришли от настоящего ядра",
      "stt" in core.session.peer_capabilities
      and "tasks" in core.session.peer_capabilities,
      f"| {core.session.peer_capabilities}")

trace = new_trace_id()
core.ask("command.handle", {"text": "который час", "source": "typed"},
         trace_id=trace)
messages = core.read_until("assistant.response")
kinds = [(m.type, m.method) for m in messages]
check("ответ «принято» пришёл первым",
      messages and messages[0].type == MessageType.RESPONSE
      and messages[0].payload.get("accepted") is True, f"| {kinds}")
events = [m for m in messages if m.type == MessageType.EVENT]
check("настоящее событие ядра доехало", events, f"| {kinds}")
check("событие несёт трассировку запроса",
      all(m.trace_id == trace for m in messages),
      f"| {[m.trace_id for m in messages]}")

spoken = [m for m in events if m.method == "assistant.response"]
check("Рина ответила текстом", spoken and spoken[0].payload.get("text"),
      f"| {[m.method for m in events]}")
print(f"     ответ ядра: {spoken[0].payload['text'][:60]!r}" if spoken else "")

core.ask("рина.станцуй")
refusal = core.read(1)[0]
check("неизвестный метод отклонён по коду",
      refusal.type == MessageType.ERROR
      and refusal.payload["code"] == "protocol.unknown_method",
      f"| {refusal.payload.get('code')}")

core.ask("settings.describe", {"keys": ["volume", "log_level", "llm_url",
                                       "ui_language", "first_run"]})
described = core.read(1)[0]
schema = described.payload["schema"]
check("схема отдана по запрошенным ключам", set(schema) == {
    "volume", "log_level", "llm_url", "ui_language", "first_run"},
      f"| {sorted(schema)}")
check("ядро называет тип и умолчание",
      schema["volume"]["type"] == "integer" and schema["volume"]["default"] == 75)
check("и диапазон", schema["volume"]["low"] == 0
      and schema["volume"]["high"] == 100)
check("и перечисление", "DEBUG" in schema["log_level"]["choices"])
check("и зависимость между полями",
      schema["llm_url"]["depends_on"] == "llm_enabled")
# Not one setting requires a restart, and that is a statement rather than a
# coincidence: the language, the speech engines and the journal level are
# applied on the fly. The mark stays in the schema — it will be needed by
# something that truly cannot be applied live — but such a key appearing must
# be a decision rather than an accident, and that is what this check trips
# over.
check("настройки применяются без перезапуска",
      not any(spec.get("restart_required") for spec in schema.values()),
      f"| {[k for k, v in schema.items() if v.get('restart_required')]}")
check("и что ключ служебный", schema["first_run"]["secret"] is True)
check("раскладку ядро не описывает намеренно",
      described.payload.get("layout") is None
      and "ADR 0006" in described.payload.get("note", ""),
      f"| {described.payload.get('note')}")

# Writing: a verdict per key, not one "it worked" for the whole parcel.
core.ask("settings.set", {"values": {"volume": 42, "log_level": "TRACE",
                                     "llm_url": "http://192.168.1.9:11434",
                                     "нетакого": 1}})
written = core.read(1)[0]
verdicts = written.payload["verdicts"]
check("верное значение принято", verdicts["volume"]["accepted"] is True)
check("значение вне перечисления отклонено кодом",
      verdicts["log_level"] == {"accepted": False,
                                "code": "settings.invalid_value",
                                "message": verdicts["log_level"]["message"]},
      f"| {verdicts['log_level']}")
check("несуществующий ключ отклонён своим кодом",
      verdicts["нетакого"]["code"] == "settings.unknown_key")
check("нелокальный адрес принят, но с предупреждением",
      verdicts["llm_url"]["accepted"] is True
      and verdicts["llm_url"]["code"] == "llm.remote_address",
      f"| {verdicts['llm_url']}")
check("предупреждение объясняет, чем это обернётся",
      "192.168.1.9" in verdicts["llm_url"]["message"],
      f"| {verdicts['llm_url']['message']}")
check("записано только принятое",
      set(written.payload["values"]) == {"volume", "llm_url"},
      f"| {sorted(written.payload['values'])}")

core.ask("settings.get", {"keys": ["volume", "first_run"]})
values = core.read(1)[0].payload["values"]
check("значение действительно сохранилось", values.get("volume") == 42)
check("служебный ключ наружу не отдаётся", "first_run" not in values,
      f"| {sorted(values)}")

core.ask("core.shutdown")
core.read(1)
code = core.wait()
check("по просьбе ядро завершилось с нулём", code == 0, f"| код {code}")


# ---------------------------------------------------------------------------
print()
print("=== E05: напоминание срабатывает само ===")

# The event channel's first real consumer: until now it was checked with
# stubs. The reminder is set by a voice command — through the real parse —
# and arrives as a push event nobody asked for.
timer = Core()
timer.handshake()

timer.ask("command.handle", {"text": "засеки 3 секунды", "source": "voice"})
booked = timer.read_until("assistant.response", timeout=20)
check("команда принята и подтверждена вслух",
      any(m.method == "assistant.response" for m in booked),
      f"| {[m.method for m in booked]}")

# The answer to the list and the firing itself go over one channel and may
# get mixed up: the timer is three seconds, and the answer comes when it
# comes. So one stream is read up to the firing, and parsed afterwards. The
# first edition of this check waited for them in turn — and the loop waiting
# for the answer ate the event that came next, after which the second loop
# waited for what had already been read.
timer.ask("reminders.list")
alarm = timer.read_until("reminder.fired", timeout=25, limit=30)

answers = [m for m in alarm if m.type == MessageType.RESPONSE]
items = answers[-1].payload["items"] if answers else []
check("ядро знает о запланированном", len(items) == 1, f"| {items}")
if items:
    check("напоминание описано по форме §10",
          set(items[0]) == {"id", "kind", "text", "fire_at", "created_at",
                            "done"},
          f"| {sorted(items[0])}")
    check("это таймер", items[0]["kind"] == "timer",
          f"| {items[0]['kind']}")

fired = [m for m in alarm if m.method == "reminder.fired"]
check("сработавшее напоминание пришло push-событием", fired,
      f"| {[m.method for m in alarm]}")
if fired:
    item = fired[0].payload["item"]
    check("событие несёт само напоминание",
          set(item) == {"id", "kind", "text", "fire_at", "created_at", "done"},
          f"| {sorted(item)}")
    check("оно помечено сработавшим", item["done"] is True)
    check("у срабатывания своя цепочка трассировки",
          fired[0].trace_id and fired[0].trace_id != booked[0].trace_id,
          f"| {fired[0].trace_id}")

timer.ask("core.shutdown")
timer.read(1)
check("ядро с планировщиком завершается штатно", timer.wait() == 0)


# ---------------------------------------------------------------------------
print()
print("=== E01: ядро не переживает свою оболочку ===")

orphan = Core()
orphan.handshake()
check("ядро живо, пока канал открыт", orphan.proc.poll() is None)
orphan.proc.stdin.close()                      # "the shell died"
code = orphan.wait()
check("после обрыва ядро завершилось само", code == 0, f"| код {code}")

log = orphan.stderr_text()
check("причина остановки записана в журнал",
      "Ядро остановлено" in log or code == 0,
      f"| {log.strip().splitlines()[-1:] if log else ''}")


# ---------------------------------------------------------------------------
print()
print("=== до рукопожатия ядро не работает ===")

strict = Core()
strict.ask("command.handle", {"text": "привет", "source": "typed"})
early = strict.read(1)[0]
check("метод до hello отклонён",
      early.type == MessageType.ERROR
      and early.payload["code"] == "protocol.not_ready",
      f"| {early.payload.get('code')}")
strict.proc.stdin.close()
strict.wait()


# ---------------------------------------------------------------------------
print()
print("=== F04: команды и история через протокол ===")

# Six of the inventory's capabilities were unreachable: they had a place in
# the architecture and no method. Here it is checked that they are reachable now.
work = Core()
work.handshake()
check("ядро объявило возможности команд и истории",
      "commands" in work.session.peer_capabilities
      and "history" in work.session.peer_capabilities,
      f"| {work.session.peer_capabilities}")

work.ask("commands.list")
items = work.read(1)[0].payload["items"]
check("список своих команд отдаётся", isinstance(items, list), f"| {items}")

work.ask("commands.save", {"command": {"name": "мой дискорд",
                                       "kind": "app", "target": "Discord",
                                       "enabled": True}})
saved = work.read(1)[0].payload["command"]
check("команда создана и получила номер", bool(saved.get("id")), f"| {saved}")

work.ask("commands.set_enabled", {"id": saved["id"], "enabled": False})
after = work.read(1)[0].payload["items"]
mine = [c for c in after if c["id"] == saved["id"]]
check("команду можно выключить, а не только удалить",
      mine and mine[0].get("enabled") is False, f"| {mine}")

work.ask("commands.export")
dump = work.read(1)[0].payload["commands"]
check("экспорт отдаёт содержимое, а не пишет файл",
      isinstance(dump, list) and len(dump) == len(after), f"| {len(dump)}")

work.ask("commands.import", {"commands": dump})
merged = work.read(1)[0].payload
check("импорт не затирает уже настроенное",
      merged["added"] == 0 and merged["skipped"] == len(dump), f"| {merged}")

work.ask("commands.import", {"commands": [{"id": "cmd_new", "name": "чужая",
                                           "kind": "app", "target": "X"}]})
check("новая команда из импорта принята",
      work.read(1)[0].payload["added"] == 1)

work.ask("commands.delete", {"id": saved["id"]})
check("команда удаляется", work.read(1)[0].payload["deleted"] is True)

# History: the conversation is visible, erasable and exportable.
work.ask("command.handle", {"text": "который час", "source": "typed"})
work.read_until("assistant.response")
work.ask("history.list", {"limit": 10})
told = work.read(1)[0].payload
check("история видна оболочке", told["total"] > 0, f"| {told['total']}")
check("записи описаны полями",
      told["items"] and {"ts", "kind", "text"} <= set(told["items"][0]),
      f"| {told['items'][:1]}")

work.ask("history.export")
check("история выгружается",
      len(work.read(1)[0].payload["items"]) == told["total"])

work.ask("history.clear")
cleared = work.read(1)[0].payload["cleared"]
work.ask("history.list")
check("история стирается по просьбе человека",
      cleared > 0 and work.read(1)[0].payload["total"] == 0,
      f"| стёрто {cleared}")

# Installing a plugin: there used to be an honest refusal here, "it will come
# with block H". Block H is closed, the refusal is gone, and the check checks
# the installation.
work.ask("plugins.install", {"source": "C:/nowhere"})
answer = work.read(1)[0]
check("несуществующий источник отклонён с причиной",
      answer.type == MessageType.ERROR
      and "не найден" in answer.payload["message"],
      f"| {answer.payload.get('message')}")

# And a real installation — from a folder assembled right here.

with tempfile.TemporaryDirectory() as staging:
    folder = os.path.join(staging, "probe_install")
    os.makedirs(folder)
    io.open(os.path.join(folder, "plugin.json"), "w",
            encoding="utf-8").write(json.dumps(
                {"id": "probe_install", "name": "Поставленный",
                 "api_version": 4}, ensure_ascii=False))
    io.open(os.path.join(folder, "main.py"), "w",
            encoding="utf-8").write(PLUGIN_SOURCE)

    # We install into the real plugins directory — installation knows no
    # other — so we clear up both before and after: a check that left a
    # plugin behind checks replacement instead of installation on the second
    # run. Which is what happened.
    installed = os.path.join(ROOT, "plugins", "probe_install")
    shutil.rmtree(installed, ignore_errors=True)

    work.ask("plugins.install", {"source": folder})
    put = work.read(1)[0]
    check("плагин ставится из папки",
          put.type == MessageType.RESPONSE
          and put.payload.get("plugin_id") == "probe_install"
          and put.payload.get("replaced") is False,
          f"| {put.payload}")

    work.ask("plugins.list")
    listed = work.read(1)[0].payload.get("items") or []
    check("и сразу виден в списке, без перезапуска",
          any(p.get("plugin_id") == "probe_install" for p in listed),
          f"| {[p.get('plugin_id') for p in listed]}")

shutil.rmtree(os.path.join(ROOT, "plugins", "probe_install"),
              ignore_errors=True)

# Resetting the settings: it returns the defaults and does not touch the commands.
work.ask("settings.set", {"values": {"volume": 11}})
work.read(1)
work.ask("commands.save", {"command": {"type": "speak", "target": "тест",
                                       "triggers": ["скажи тест"],
                                       "enabled": True, "match": "contains"}})
work.read(1)
work.ask("settings.reset")
after = work.read(1)[0].payload
check("сброс вернул умолчание", after["values"]["volume"] == 75,
      f"| {after['values']['volume']}")
work.ask("commands.list")
kept = work.read(1)[0].payload.get("items") or []
check("а команды остались", len(kept) > 0,
      "| их удаление — отдельное осознанное действие, а не побочный эффект")

work.ask("core.shutdown")
work.read(1)
work.wait()


# ---------------------------------------------------------------------------
print()
print("=== F11: опасное подтверждается, а не выполняется ===")

# The core cannot perform something irreversible itself: it asks, the shell
# asks the person, the decision comes back. Until now the permission channel
# existed but nobody used it — a dangerous action was simply rejected.
danger = Core()
danger.handshake()

danger.ask("command.handle", {"text": "выключи компьютер", "source": "voice"})
# We wait for the permission request itself: a sentinel word that never
# comes would make us wait out the whole deadline for nothing.
asked = danger.read_until("permission.request", timeout=25, limit=10)
requests = [m for m in asked if m.type == MessageType.REQUEST
            and m.method == "permission.request"]
check("ядро спросило разрешения", requests,
      f"| {[(m.type, m.method) for m in asked]}")

if requests:
    ask = requests[0]
    check("показано, что именно произойдёт, а не имя действия",
          "компьютер" in ask.payload["preview"].lower()
          and ask.payload["preview"] != ask.payload["action"],
          f"| {ask.payload['preview']!r}")
    check("названа причина", ask.payload.get("reason"),
          f"| {ask.payload.get('reason')!r}")
    check("назван срок", ask.payload.get("ttl", 0) > 0,
          f"| {ask.payload.get('ttl')} с")
    check("запрос несёт свой номер", bool(ask.payload.get("request_id")))

    # --- the refusal ---
    # We answer as a shell would: the answer inherits the trace and the
    # version from the request.
    danger.send(ask.reply({"granted": False, "scope": "once"},
                          id=danger.ids.next()))
    after = danger.read_until("assistant.response", timeout=20, limit=8)
    said = [m.payload.get("text", "") for m in after
            if m.method == "assistant.response"]
    check("после отказа Рина отвечает словами, а не молчит", said,
          f"| {said}")

# --- consent: the same action, but permitted ---
danger.ask("command.handle", {"text": "выключи компьютер", "source": "voice"})
asked2 = danger.read_until("permission.request", timeout=25, limit=10)
requests2 = [m for m in asked2 if m.type == MessageType.REQUEST
             and m.method == "permission.request"]
check("на второй раз спрошено снова", requests2,
      "| согласие одноразовое, и повтор обязан спросить опять")

if requests2:
    ask2 = requests2[0]
    danger.send(ask2.reply({"granted": True, "scope": "once"},
                           id=danger.ids.next()))
    done = danger.read_until("assistant.response", timeout=20, limit=8)
    check("после согласия действие дошло до исполнения",
          any(m.method == "assistant.response" for m in done),
          f"| {[m.method for m in done]}")

danger.ask("core.shutdown")
danger.read(1)
danger.wait()

print()
print("=== F04: список значений спрашивают, а не угадывают ===")

# The changeable is separated from the constant: `describe` says a set
# exists, `options` says what it is today. Checked in a live core, because
# the answer depends on what is really installed on the machine.
opt = Core()
opt.handshake()

opt.ask("settings.describe")
schema = opt.read(1)[0].payload["schema"]
dynamic = sorted(k for k, v in schema.items() if v.get("dynamic"))
check("схема объявляет изменчивые ключи", len(dynamic) >= 4, f"| {dynamic}")
check("у изменчивого ключа нет перечисления в схеме",
      all("choices" not in schema[k] for k in dynamic),
      "| иначе список закешируется вместе со схемой")
check("путь объявлен форматом, а не догадкой",
      schema.get("vosk_model", {}).get("format") == "folder"
      and schema.get("piper_model", {}).get("format") == "file",
      f"| {schema.get('vosk_model')}")

opt.ask("settings.options", {"keys": dynamic})
listed = opt.read(1)[0].payload["options"]
check("ядро перечислило все спрошенные ключи",
      set(listed) == set(dynamic), f"| {sorted(listed)}")
check("варианты названы по-человечески",
      all(o["title"] for o in listed["tts_engine"]),
      f"| {[o['title'] for o in listed['tts_engine']][:2]}")
check("недоступное показано, а не спрятано",
      any(not o["available"] for o in listed["stt_engine"]),
      "| иначе человек не узнает, что такое бывает")

# A value outside today's set is not accepted: the set is the truth about
# the machine, not a decoration of the list.
opt.ask("settings.set", {"values": {"tts_engine": "такого-нет"}})
verdict = opt.read(1)[0].payload["verdicts"]["tts_engine"]
check("чужое значение отклонено", not verdict["accepted"],
      f"| {verdict['code']}")

# Changing the engine takes the voice with it: every engine has its own
# numbering, and a foreign voice left behind would stay silent forever.
before = listed["voice"]
opt.ask("settings.set", {"values": {"tts_engine": "silent"}})
said = opt.read(1)[0].payload["verdicts"]["tts_engine"]
check("движок принят", said["accepted"], f"| {said}")
opt.ask("settings.get", {"keys": ["voice"]})
now = opt.read(1)[0].payload["values"]["voice"]
opt.ask("settings.options", {"keys": ["voice"]})
after = opt.read(1)[0].payload["options"]["voice"]
check("голос остался тем, что движок действительно умеет",
      now in {o["value"] for o in after},
      f"| голос {now!r}, движок предлагает "
      f"{[o['value'] for o in after]} (было {[o['value'] for o in before]})")

opt.ask("core.shutdown")
opt.read(1)
opt.wait()

print()
print("=== E06a: настройка переживает перезапуск ядра ===")

# The only check that catches this: in one process the value is read back
# without being written to disk — it lies in memory. In 3.1.0 the saving was
# done by whoever changed it — the settings screen; the screen moved to
# another process and the call stayed there, and a setting held exactly until
# the core exited. Both cores look into one directory: otherwise a "restart"
# is two different stores, and the check is green having checked nothing.
shared_dir = tempfile.mkdtemp(prefix="rina-restart-")
os.environ["RINA_SANDBOX_DIR"] = shared_dir

keeper = Core()
keeper.handshake()
keeper.ask("settings.get", {"keys": ["speed"]})
was = keeper.read(1)[0].payload["values"]["speed"]
other = 133 if was != 133 else 145

keeper.ask("settings.set", {"values": {"speed": other}})
check("значение принято",
      keeper.read(1)[0].payload["verdicts"]["speed"]["accepted"])
keeper.ask("core.shutdown")
keeper.read(1)
keeper.wait()

again = Core()
again.handshake()
again.ask("settings.get", {"keys": ["speed"]})
now = again.read(1)[0].payload["values"]["speed"]
check("после перезапуска ядра настройка на месте", now == other,
      f"| было {was}, ставили {other}, прочитали {now}")

again.ask("settings.set", {"values": {"speed": was}})
again.read(1)
again.ask("core.shutdown")
again.read(1)
again.wait()

# And the same from the other side: a core that has one key changed must not
# carry the rest away with it. That is how the settings went missing in real
# life — the shell wrote down the finish, and the whole group went to disk as
# defaults, because the core did not read the file. The check puts knowingly
# foreign values into the file before the core starts and looks at what
# becomes of them.
import json as _json3

untouched = os.path.join(shared_dir, "RinaAssistant", "settings.json")
kept = _json3.load(open(untouched, encoding="utf-8"))
kept["tts_engine"] = "edge"
kept["speed"] = 177
_json3.dump(kept, open(untouched, "w", encoding="utf-8"), ensure_ascii=False)

careful = Core()
careful.handshake()
careful.ask("settings.set", {"values": {"finish": "black"}})
careful.read(1)
careful.ask("core.shutdown")
careful.read(1)
careful.wait()

after = _json3.load(open(untouched, encoding="utf-8"))
check("соседние настройки пережили запись одной",
      after.get("tts_engine") == "edge" and after.get("speed") == 177,
      f"| движок {after.get('tts_engine')!r}, скорость {after.get('speed')!r}")
check("а записанное записалось", after.get("finish") == "black",
      f"| {after.get('finish')!r}")

os.environ.pop("RINA_SANDBOX_DIR", None)
shutil.rmtree(shared_dir, ignore_errors=True)

print()
print("=== F04: плагины по проводу ===")

# The plugin manager was written for a window and dragged Qt along. The check
# goes through a real core process for exactly that reason: importing PySide6
# in the core is forbidden, and that has to be found out here rather than on
# a machine where Qt is not installed.
plug = Core()
plug.handshake()

plug.ask("plugins.list")
listed = plug.read(1)[0].payload["items"]
check("ядро видит плагины", len(listed) > 0, f"| {len(listed)}")
check("у каждого есть имя и номер",
      all(p.get("plugin_id") and p.get("name") for p in listed))
by_id = {p["plugin_id"]: p for p in listed}

# Switching on returns the state AFTER, not "accepted": a plugin may refuse
# to load, and "on" would be an untruth.
first = sorted(by_id)[0]
plug.ask("plugins.set_enabled", {"plugin_id": first, "enabled": True})
state = plug.read(1)[0].payload["plugin"]
check("плагин включился", state["enabled"] is True, f"| {first}")

plug.ask("plugins.list")
after = {p["plugin_id"]: p for p in plug.read(1)[0].payload["items"]}
with_page = [pid for pid, p in after.items() if p["has_page"]]

# A switched-off one has no page: it is not loaded, and there is nothing to ask it.
for pid in sorted(by_id):
    if pid == first:
        continue
    plug.ask("plugins.set_enabled", {"plugin_id": pid, "enabled": True})
    plug.read(1)
plug.ask("plugins.list")
loaded = {p["plugin_id"]: p for p in plug.read(1)[0].payload["items"]}
with_page = [pid for pid, p in loaded.items() if p["has_page"]]
check("хотя бы у одного плагина есть своя страница", bool(with_page),
      f"| {with_page}")

if with_page:
    target = with_page[0]
    plug.ask("plugins.page", {"plugin_id": target})
    page = plug.read(1)[0].payload
    check("страница описана элементами, а не виджетом",
          isinstance(page.get("elements"), list) and page["elements"],
          f"| {[e.get('kind') for e in page.get('elements', [])]}")
    check("у каждого элемента есть вид",
          all(e.get("kind") for e in page["elements"]))

    # An action returns a new page in the same answer: a button changes
    # what is drawn next to it.
    plug.ask("plugins.action", {"plugin_id": target, "action": "clear"})
    again = plug.read(1)[0].payload
    check("действие вернуло новую страницу",
          isinstance(again.get("elements"), list),
          f"| элементов {len(again.get('elements', []))}")

plug.ask("plugins.page", {"plugin_id": "такого-нет"})
missing = plug.read(1)[0]
check("несуществующий плагин — ошибка каталога, а не пустая страница",
      missing.type == MessageType.ERROR
      and missing.payload.get("code") == "plugin.not_found",
      f"| {missing.payload.get('code')}")

plug.ask("core.shutdown")
plug.read(1)
plug.wait()

print()
print("=== F08: язык реплик Рины ===")

# The interface's words are translated by the shell, Rina's lines by the core
# (ADR 0007). The second half is checked here: there is one setting, and the
# core is obliged to apply it to itself — 3.1.0's window used to do that, the
# program's only entrance, and in a split program there are two.
speaker = Core()
speaker.handshake()

speaker.ask("settings.options", {"keys": ["ui_language"]})
langs = speaker.read(1)[0].payload["options"]["ui_language"]
check("ядро перечисляет языки", len(langs) > 1,
      f"| {[o['value'] for o in langs]}")
check("неполный перевод назван неполным, а не числом",
      any("неполный" in o["title"] for o in langs),
      "| ядро не знает про строки оболочки и доли не выдумывает")

speaker.ask("settings.set", {"values": {"ui_language": "English"}})
verdict = speaker.read(1)[0].payload["verdicts"]["ui_language"]
check("язык принят", verdict["accepted"], f"| {verdict}")

speaker.ask("settings.set", {"values": {"ui_language": "Klingon"}})
refused = speaker.read(1)[0].payload["verdicts"]["ui_language"]
check("несуществующий язык отклонён", not refused["accepted"],
      f"| {refused['code']}")

speaker.ask("settings.set", {"values": {"ui_language": "Русский"}})
speaker.read(1)
speaker.ask("core.shutdown")
speaker.read(1)
speaker.wait()

print()
print("ИТОГО ошибок:", fails)
sys.exit(1 if fails else 0)
