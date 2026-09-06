# -*- coding: utf-8 -*-
"""
The protocol's conformance tests: the twelve requirements of §15.

Plan item 4.0-D16.

How this differs from tools/test_wire.py. That one checks the parts
separately, calling them directly. Here both sides see **only bytes**: every
message goes through encode_frame -> the transport -> FrameDecoder, and
neither side looks into the other's objects. A requirement fulfilled by
calling a function but not fulfilled over the wire is not fulfilled.

An in-process transport, not a named pipe. ADR 0002 requires this: the
protocol does not depend on the transport, and conformance is obliged to
prove that rather than assume it. The suite also runs in milliseconds and
leaves no processes behind.

No threads. Delivery is explicit — `deliver()` carries the accumulated bytes
from one side's outgoing buffer into the other's incoming parse. Threads
would give a non-deterministic order, and conformance is obliged to fail the
same way every time.

**The core is real where that matters.** The confirmation gates are that
very `core/toolrunner.py` the application uses; a stub in its place would be
checking a stub. The shell here is a mock: the real one does not exist yet
(`4.0-F02`), and when it appears the suite is set on it without rewriting
the requirements.

To run:
    python tools/conformance.py
"""

import os
import sys

from console import use_utf8

use_utf8()

ROOT = r"C:\DevStation\PCDev\DesktopApps\RinaAssistant"
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
os.chdir(ROOT)

from core import logging_setup
logging_setup.setup()

from sandbox import neutralise
box = neutralise()

import time

from core.confirmations import ONCE, UNTIL, ConfirmationLedger
from core.settings_api import MemorySettings
from core.toolrunner import ToolContext, ToolRunner
from core.wire import (DataFrameDecoder, DataSender, Envelope, FrameDecoder,
                       IdGenerator, Liveness, MessageType, PermissionChannel,
                       ProtocolFault, Registry, Router, Session, SessionState,
                       Side, StreamSender, VolatileState, encode_frame, event,
                       make, negotiate, new_trace_id, trace_scope)
from core.wire.errors import (ERROR_INCOMPATIBLE, ERROR_INVALID_ENVELOPE,
                              ERROR_NOT_READY, ERROR_UNKNOWN_METHOD)
from core.wire.tasks import TaskState, run as run_task

fails = 0
checks = 0


def check(label, cond, detail=""):
    global fails, checks
    checks += 1
    if not cond:
        fails += 1
    print(("  OK   " if cond else "  FAIL "), label, detail)


def requirement(number, title):
    print()
    print(f"=== §15.{number} — {title} ===")


# ---------------------------------------------------------------------------
# The in-process transport
# ---------------------------------------------------------------------------
class Endpoint:
    """
    One side: the session, the message numbers, the buffers of both
    channels.

    It gives out only bytes. Everything a side "knows" about its
    correspondent was obtained by parsing the frames that arrived, not by
    reaching into its objects.
    """

    def __init__(self, side, prefix, versions=(1,), capabilities=None):
        self.side = side
        self.session = Session(side=side, versions=list(versions),
                               capabilities=tuple(capabilities or ()))
        self.ids = IdGenerator(prefix)
        self.control_out = bytearray()
        self.data_out = bytearray()
        self.control_in = FrameDecoder()
        self.data_in = DataFrameDecoder()
        self.liveness = Liveness()
        self.received = []

    def send(self, envelope):
        self.control_out.extend(encode_frame(envelope))
        return envelope

    def send_data(self, raw):
        self.data_out.extend(raw)


def deliver(src, dst):
    """Carry the control bytes across and return the parsed messages."""
    raw, src.control_out = bytes(src.control_out), bytearray()
    got = list(dst.control_in.feed(raw))
    dst.received.extend(got)
    for message in got:
        dst.liveness.note_traffic()
    return got


def deliver_data(src, dst):
    raw, src.data_out = bytes(src.data_out), bytearray()
    return list(dst.data_in.feed(raw))


def one(messages, what="сообщение"):
    assert len(messages) == 1, f"ожидалось одно {what}, пришло {len(messages)}"
    return messages[0]


# ---------------------------------------------------------------------------
# The reference core
# ---------------------------------------------------------------------------
class ReferenceCore:
    """
    A core that answers by the protocol.

    A thin stand-in for `4.0-E02`, which does not exist yet: it parses the
    envelope, guards the handshake and the capabilities, and hands a
    dangerous action to the real `ToolRunner` — the confirmation gates are
    obliged to be the same as in the application, or a stub is what gets
    checked.
    """

    def __init__(self, store=None, capabilities=None, versions=(1,),
                 clock=None):
        self.endpoint = Endpoint(Side.CORE, "c-", versions, capabilities)
        self.store = store if store is not None else {}
        settings = MemorySettings()
        from voice.reminders import ReminderStore
        from voice.user_commands import UserCommandStore
        # One clock for the confirmation ledger and for the permission
        # channel: two time scales in one loop mean a deadline computed on
        # one and checked on the other.
        clock = clock or time.time
        ledger = ConfirmationLedger(clock=clock)
        #: Who to ask about a system action. Set by the test after the shell
        #: is created: a core without a correspondent does not touch the
        #: machine at all (ADR 0009), and that is a property of it rather
        #: than an unfinished job.
        self.peer = None
        self.runner = ToolRunner(ToolContext(
            settings=settings,
            reminders=ReminderStore(settings),
            commands=UserCommandStore(settings),
            emit=lambda name, **data: None,
            system_out=self._ask_shell_do,
            launch_app=self._ask_shell_launch,
        ), confirmations=ledger)
        self.permissions = PermissionChannel(ledger=ledger, clock=clock)
        self.tasks = Registry(self.endpoint.ids)
        self.data = DataSender()
        self.text = StreamSender(self.endpoint.ids)
        self.volatile = VolatileState(
            permissions=self.permissions, tasks=self.tasks,
            data_streams=self.data, text_streams=self.text,
            session=self.endpoint.session)

    @property
    def session(self):
        return self.endpoint.session

    def _round_trip(self, method, payload):
        """
        Ask the shell and wait for an answer — over the wire.

        The round is synchronous, because both ends are in one thread here:
        the request is put into a buffer, delivered, served, and the answer
        delivered back. A real core does the same with a worker thread
        (`ask_shell_sync`), but what is checked here is not multithreading
        but that the request **went and came back**.
        """
        if self.peer is None:
            return {}
        self.session.check_outgoing(method)
        request = self.endpoint.send(Envelope.request(
            method, dict(payload), id=self.endpoint.ids.next()))

        for message in deliver(self.endpoint, self.peer.endpoint):
            if message.id != request.id:
                continue
            reply = self.peer.serve(message)
            if reply is None:
                return {}
            self.peer.endpoint.send(reply)
            for back in deliver(self.peer.endpoint, self.endpoint):
                if back.correlation_id == request.id:
                    return dict(back.payload)
        return {}

    def _ask_shell_do(self, action):
        answer = self._round_trip("system.do", {"action": action})
        return bool(answer.get("ok")), str(answer.get("detail", ""))

    def _ask_shell_launch(self, launch, kind="file"):
        answer = self._round_trip("apps.launch",
                                  {"launch": launch, "kind": kind})
        return bool(answer.get("ok")), str(answer.get("reason", ""))

    def handle(self, raw_or_envelope):
        """Handle one incoming message, return the answers (a list)."""
        message = raw_or_envelope
        out = []
        with trace_scope(message.trace_id):
            try:
                self.session.check_incoming(message.method or "")
            except ProtocolFault as exc:
                out.append(self.endpoint.send(
                    message.fail(exc.error, id=self.endpoint.ids.next())))
                return out

            method = message.method
            if method == "hello":
                payload = self.session.handle_hello(message.payload)
                out.append(self.endpoint.send(
                    message.reply(payload, id=self.endpoint.ids.next())))
            elif method == "settings.set":
                self.store.update(message.payload.get("values") or {})
                out.append(self.endpoint.send(message.reply(
                    {"values": dict(self.store)}, id=self.endpoint.ids.next())))
            elif method == "settings.get":
                out.append(self.endpoint.send(message.reply(
                    {"values": dict(self.store)}, id=self.endpoint.ids.next())))
            elif method == "command.handle":
                out.extend(self._command(message))
            elif method == "task.cancel":
                answer = self.tasks.cancel(message.payload.get("task_id", ""))
                out.append(self.endpoint.send(
                    message.reply(answer, id=self.endpoint.ids.next())))
            elif method == "ping":
                out.append(self.endpoint.send(
                    message.reply({}, id=self.endpoint.ids.next())))
            else:
                out.append(self.endpoint.send(message.fail(
                    make(ERROR_UNKNOWN_METHOD, f"метод {method!r} не обслужен"),
                    id=self.endpoint.ids.next())))
        return out

    def _command(self, message):
        """
        One command, mapped to one tool call.

        The real phrase parsing lives in the router and is checked by the
        golden suite; what matters here is something else — that the
        confirmation gates stand on the path from the wire to the execution.
        """
        out = []
        text = message.payload.get("text", "")
        confirmation_id = message.payload.get("confirmation_id") or None
        if text == "усыпи компьютер":
            result = self.runner.call(
                "power_action", {"action": "sleep"},
                confirmation_id=confirmation_id,
                source=message.payload.get("source", "typed"),
                trace_id=message.trace_id)
            if result.ok:
                out.append(self.endpoint.send(message.reply(
                    {"text": result.message}, id=self.endpoint.ids.next())))
            else:
                out.append(self.endpoint.send(message.fail(
                    make(result.error_code, result.message),
                    id=self.endpoint.ids.next())))
            out.append(self.endpoint.send(event(
                "assistant.response", {"text": result.message or "готово"},
                id=self.endpoint.ids.next())))
        else:
            out.append(self.endpoint.send(message.reply(
                {"accepted": True}, id=self.endpoint.ids.next())))
            out.append(self.endpoint.send(event(
                "assistant.response", {"text": "готово"},
                id=self.endpoint.ids.next())))
        return out


class ReferenceShell:
    """A stub shell: it can say hello, ask and listen."""

    def __init__(self, versions=(1,), capabilities=None):
        self.endpoint = Endpoint(Side.SHELL, "s-", versions, capabilities)
        self.events = Router()
        self.heard = []
        self.done = []          # system actions the core asked for
        self.launched = []      # what was asked to be launched
        for name in ("assistant.response", "task.progress", "task.partial",
                     "task.done", "task.failed", "task.cancelled"):
            self.events.on(name, lambda p, n=name: self.heard.append(n))

    @property
    def session(self):
        return self.endpoint.session

    def ask(self, method, payload=None, trace_id=None):
        return self.endpoint.send(Envelope.request(
            method, dict(payload or {}), id=self.endpoint.ids.next(),
            trace_id=trace_id))

    #: What the shell was asked to do to the machine (`4.0-G01`, ADR 0009).
    #: The core no longer touches the system itself, and the check "it
    #: reached the system layer" now looks precisely here.
    def serve(self, request):
        """Answer a request from the core the way a real shell would."""
        if request.method == "system.do":
            action = request.payload.get("action", "")
            self.done.append(action)
            return request.reply({"ok": True, "detail": ""},
                                 id=self.endpoint.ids.next())
        if request.method == "apps.index":
            return request.reply({"entries": []},
                                 id=self.endpoint.ids.next())
        if request.method == "apps.launch":
            self.launched.append(request.payload.get("launch", ""))
            return request.reply({"ok": True, "reason": ""},
                                 id=self.endpoint.ids.next())
        return None


def handshake(shell, core):
    """Carry out the handshake over the wire. Returns the core's answer."""
    with trace_scope() as trace:
        shell.ask("hello", shell.session.hello_payload(), trace_id=trace)
    incoming = one(deliver(shell.endpoint, core.endpoint), "hello")
    core.handle(incoming)
    answer = one(deliver(core.endpoint, shell.endpoint), "ответ на hello")
    if answer.type == MessageType.ERROR:
        return answer
    shell.session.accept_hello_result(answer.payload)
    return answer


def talk(shell, core, method, payload=None, trace_id=None):
    """
    The shell's request -> handling by the core -> everything that came back.

    The core's counter-requests (`system.do`, `apps.launch`) are served
    inside the handling: since `4.0-G01` a system action is performed not in
    the core but on the other side of the wire, and the tool needs the
    outcome immediately.
    """
    shell.ask(method, payload, trace_id=trace_id)
    for message in deliver(shell.endpoint, core.endpoint):
        core.handle(message)

    return deliver(core.endpoint, shell.endpoint)


# ---------------------------------------------------------------------------
print("=== D16: conformance-тесты протокола ===")
print("транспорт внутри процесса, обе стороны видят только байты")

# --- 1 ---------------------------------------------------------------------
requirement(1, "полный конверт на каждом сообщении")

shell, core = ReferenceShell(), ReferenceCore()
core.peer = shell
handshake(shell, core)
check("рукопожатие прошло", shell.session.ready and core.session.ready)

answers = talk(shell, core, "command.handle",
               {"text": "который час", "source": "typed"})
required = ("v", "type", "id", "timestamp", "trace_id", "payload")
missing = [f for m in answers for f in required if f not in m.to_dict()]
check("во всех ответах полный конверт", not missing, f"| {missing}")

# A broken message, assembled by hand around the constructor.
import json as _json

broken = _json.dumps({"v": 1, "type": "request", "method": "command.handle",
                      "payload": {}}).encode("utf-8")
frame = len(broken).to_bytes(4, "big") + broken
caught = None
try:
    list(FrameDecoder().feed(frame))
except ProtocolFault as exc:
    caught = exc.error
check("конверт без обязательных полей отвергнут",
      caught is not None and caught.code == ERROR_INVALID_ENVELOPE,
      f"| {caught.details if caught else 'не отвергнут'}")
check("отвергнут именно как протокольная ошибка",
      caught is not None and caught.category == "protocol")

# --- 2 ---------------------------------------------------------------------
requirement(2, "неизвестный метод — ошибка, неизвестное событие — молчание")

answers = talk(shell, core, "рина.станцуй")
bad = one(answers, "ответ")
check("неизвестный метод даёт ошибку",
      bad.type == MessageType.ERROR
      and bad.payload["code"] == ERROR_UNKNOWN_METHOD,
      f"| {bad.payload.get('code')}")
check("ошибка ссылается на свой запрос", bad.correlation_id is not None)

future = Envelope.event("рина.загрустила", {"уровень": 3},
                        id="c-999", trace_id=new_trace_id())
core.endpoint.send(future)
delivered = one(deliver(core.endpoint, shell.endpoint), "событие")
check("незнакомое событие получено, но не доставлено подписчикам",
      shell.events.dispatch(delivered) is False)
check("оно записано как проигнорированное",
      shell.events.ignored == ["рина.загрустила"])

# --- 3 ---------------------------------------------------------------------
requirement(3, "несовместимая версия — внятное сообщение, а не обрыв")

new_shell = ReferenceShell(versions=(2,))
old_core = ReferenceCore(versions=(1,))
with trace_scope() as trace:
    new_shell.ask("hello", new_shell.session.hello_payload(), trace_id=trace)
incoming = one(deliver(new_shell.endpoint, old_core.endpoint), "hello")
replies = []
try:
    old_core.handle(incoming)
    replies = deliver(old_core.endpoint, new_shell.endpoint)
except ProtocolFault as exc:
    replies = [exc.error]
check("канал не оборван, ответ пришёл", len(replies) == 1)
text = getattr(replies[0], "payload", {}).get("message", "") \
    if hasattr(replies[0], "payload") else replies[0].message
check("сообщение называет обе стороны",
      "2" in text and "1" in text, f"| {text}")
check("оболочка так и не стала готовой", not new_shell.session.ready)

# --- 3a --------------------------------------------------------------------
requirement("3a", "оболочка [1,2] работает со старым ядром по версии 1")

stepped_shell = ReferenceShell(versions=(1, 2))
stepped_core = ReferenceCore(versions=(1,))
answer = handshake(stepped_shell, stepped_core)
check("рукопожатие удалось", stepped_shell.session.ready)
check("выбрана версия 1", stepped_shell.session.version == 1)
answers = talk(stepped_shell, stepped_core, "command.handle",
               {"text": "который час", "source": "typed"})
check("и работа идёт", any(m.type == MessageType.RESPONSE for m in answers))
check("все сообщения помечены выбранной версией",
      all(m.v == 1 for m in answers), f"| {[m.v for m in answers]}")

# --- 4 ---------------------------------------------------------------------
requirement(4, "необъявленная возможность не вызывается")

deaf_core = ReferenceCore(capabilities=("tts", "reminders"))
picky_shell = ReferenceShell()
handshake(picky_shell, deaf_core)
check("ядро без stt объявило это в рукопожатии",
      "stt" not in picky_shell.session.peer_capabilities,
      f"| {picky_shell.session.peer_capabilities}")
check("оболочка сама не станет звать speech.listen_once",
      not picky_shell.session.may_call("speech.listen_once"))

# And if it does call — the core refuses with the same code.
picky_shell.ask("speech.listen_once", {})
for message in deliver(picky_shell.endpoint, deaf_core.endpoint):
    deaf_core.handle(message)
refusal = one(deliver(deaf_core.endpoint, picky_shell.endpoint), "отказ")
check("ядро отвечает «неизвестный метод»",
      refusal.type == MessageType.ERROR
      and refusal.payload["code"] == ERROR_UNKNOWN_METHOD)

# --- 5 ---------------------------------------------------------------------
requirement(5, "отправитель не превышает выданный кредит")

audio = DataSender()
audio.open_stream(11, "audio.input")
check("до кредита не отправляется ни байта", audio.available(11) == 0)
audio.grant(11, 2048)
chunk = b"\x00\x01" * 512                       # 1024 bytes
shell.endpoint.send_data(audio.send(11, chunk))
shell.endpoint.send_data(audio.send(11, chunk))
overflow = None
try:
    audio.send(11, chunk)
except ProtocolFault as exc:
    overflow = exc.error
check("третий кадр сверх кредита не выпущен", overflow is not None,
      f"| {overflow.code if overflow else 'выпущен'}")
frames = deliver_data(shell.endpoint, core.endpoint)
check("в канал ушло ровно то, на что был кредит",
      sum(len(f.payload) for f in frames) == 2048, f"| {len(frames)} кадра")
check("порядковые номера подряд", [f.seq for f in frames] == [1, 2])

# --- 6 ---------------------------------------------------------------------
requirement(6, "поток PCM не задерживает управляющий канал")

burst = DataSender()
burst.open_stream(12, "audio.input")
burst.grant(12, 300 * len(chunk))
for _ in range(300):
    shell.endpoint.send_data(burst.send(12, chunk))
shell.ask("command.handle", {"text": "стоп", "source": "voice"})

control_bytes = len(shell.endpoint.control_out)
data_bytes = len(shell.endpoint.data_out)
got = deliver(shell.endpoint, core.endpoint)
check("команда разобрана до того, как тронут звук",
      len(got) == 1 and got[0].payload["text"] == "стоп")
check("управляющий разбор не читал байтов звука",
      control_bytes < data_bytes / 100,
      f"| управление {control_bytes} Б, звук {data_bytes} Б")
check("звук всё ещё ждёт в своём канале", len(shell.endpoint.data_out) > 0)
deliver_data(shell.endpoint, core.endpoint)
for message in got:
    core.handle(message)
deliver(core.endpoint, shell.endpoint)

# --- 7 ---------------------------------------------------------------------
requirement(7, "долгая задача: прогресс, промежуточный, одно завершение")

clock = [0.0]
job = core.tasks.create()
with trace_scope() as job_trace:
    produced = run_task(job, steps=12, clock=lambda: clock[0],
                        advance=lambda d: clock.__setitem__(0, clock[0] + d),
                        seconds=60.0, partial_every=4)
for message in produced:
    core.endpoint.send(message)
arrived = deliver(core.endpoint, shell.endpoint)
for message in arrived:
    shell.events.dispatch(message)

kinds = [m.method for m in arrived]
check("часы прошли шестьдесят секунд", clock[0] == 60.0)
check("прогресс доехал", kinds.count("task.progress") == 12)
check("промежуточные результаты доехали", kinds.count("task.partial") == 3)
finals = [k for k in kinds if k in ("task.done", "task.failed",
                                    "task.cancelled")]
check("ровно одно финальное событие", finals == ["task.done"], f"| {finals}")
check("оболочка услышала всё", shell.heard.count("task.progress") == 12)

# --- 8 ---------------------------------------------------------------------
requirement(8, "отмена: подтверждение, затем cancelled; поздняя — нет")

running = core.tasks.create()
running.start()
answers = talk(shell, core, "task.cancel", {"task_id": running.id})
ack = one(answers, "подтверждение")
check("подтверждение получения пришло",
      ack.type == MessageType.RESPONSE and ack.payload["accepted"] is True)
check("задача ещё не завершена", not running.finished)
core.endpoint.send(running.cancelled())
stop = one(deliver(core.endpoint, shell.endpoint), "cancelled")
check("остановка пришла отдельным событием",
      stop.method == "task.cancelled")
check("у задачи ровно одно финальное событие",
      len([m for m in running.events if m.method.startswith("task.")
           and m.method in ("task.done", "task.failed", "task.cancelled")]) == 1)

quick = core.tasks.create()
quick.start()
core.endpoint.send(quick.done({"итог": "успел"}))
deliver(core.endpoint, shell.endpoint)
answers = talk(shell, core, "task.cancel", {"task_id": quick.id})
late = one(answers, "ответ")
check("отмена завершённой не принята",
      late.payload == {"accepted": False, "status": TaskState.DONE},
      f"| {late.payload}")
check("task.cancelled так и не пришёл",
      [m.method for m in quick.events] == ["task.done"])

# --- 9 ---------------------------------------------------------------------
requirement(9, "опасное действие без подтверждения отклоняется")

answers = talk(shell, core, "command.handle",
               {"text": "усыпи компьютер", "source": "voice"})
refusal = [m for m in answers if m.type == MessageType.ERROR]
check("пришла ошибка, а не исполнение", len(refusal) == 1,
      f"| {[m.type for m in answers]}")
check("код — «требуется подтверждение»",
      refusal and refusal[0].payload["code"] == "confirmation.required",
      f"| {refusal[0].payload['code'] if refusal else '—'}")
check("компьютер не тронут", box.actions == [], f"| {box.actions}")

# Now with a confirmation issued by the core through the permission channel.
ask = core.permissions.ask("power_action", {"action": "sleep"},
                           permission="system.power",
                           reason="Пользователь сказал «усыпи компьютер»",
                           preview="Компьютер уснёт немедленно.")
core.endpoint.send(Envelope.request("permission.request", ask.to_payload(),
                                    id=core.endpoint.ids.next(),
                                    trace_id=new_trace_id()))
asked = one(deliver(core.endpoint, shell.endpoint), "просьба")
check("просьба показывает, что именно произойдёт",
      asked.payload["preview"].startswith("Компьютер уснёт"))
check("аргументы вызова в просьбу не попали",
      "sleep" not in str(asked.payload))
decision = core.permissions.resolve(asked.payload["request_id"], True, ONCE)
answers = talk(shell, core, "command.handle",
               {"text": "усыпи компьютер", "source": "voice",
                "confirmation_id": decision["confirmation_id"]})
ok = [m for m in answers if m.type == MessageType.RESPONSE]
check("с подтверждением действие исполнено", len(ok) == 1,
      f"| {[m.type for m in answers]}")
check("и оно действительно дошло до системного слоя",
      shell.done == ["sleep"], f"| {shell.done}")
check("а ядро само машину не трогало",
      box.actions == [],
      "| системный вызов из ядра — то, чего ADR 0009 не допускает")

# --- 10 --------------------------------------------------------------------
requirement(10, "просроченное подтверждение отклоняется")

# A core with a fake clock: the deadline is checked rather than waited out.
# The first edition of this check failed, and the failure was real — the
# confirmation ledger ran on system time and the permission channel on its
# own.
late_clock = [1000.0]
slow_core = ReferenceCore(clock=lambda: late_clock[0])
slow_shell = ReferenceShell()
handshake(slow_shell, slow_core)

ask = slow_core.permissions.ask("power_action", {"action": "sleep"},
                                permission="system.power", reason="…",
                                preview="Компьютер уснёт немедленно.", ttl=60)
granted = slow_core.permissions.resolve(ask.id, True, ONCE)
check("подтверждение выдано и живо",
      slow_core.runner._confirmations.pending() == 1)

box.clear()
late_clock[0] += 120                      # the window has passed
answers = talk(slow_shell, slow_core, "command.handle",
               {"text": "усыпи компьютер", "source": "voice",
                "confirmation_id": granted["confirmation_id"]})
refusal = [m for m in answers if m.type == MessageType.ERROR]
check("просроченное не принято", len(refusal) == 1,
      f"| {[m.type for m in answers]}")
check("код говорит о подтверждении",
      refusal and refusal[0].payload["code"].startswith("confirmation."),
      f"| {refusal[0].payload['code'] if refusal else '—'}")
check("компьютер снова не тронут", box.actions == [], f"| {box.actions}")

# --- 11 --------------------------------------------------------------------
requirement(11, "падение ядра: перезапуск без потери пользовательских данных")

store = {}
shell2 = ReferenceShell()
core2 = ReferenceCore(store=store)
handshake(shell2, core2)
talk(shell2, core2, "settings.set", {"values": {"голос": "Рина", "темп": 1.1}})

live_ask = core2.permissions.ask("power_action", {"action": "sleep"},
                                 permission="system.power", reason="…",
                                 preview="Компьютер уснёт немедленно.")
live_grant = core2.permissions.resolve(live_ask.id, True, ONCE)
task_before = core2.tasks.create()
task_before.start()
check("до падения есть и данные, и летучее состояние",
      store and core2.volatile.snapshot()["задачи"] == 1)

was = core2.volatile.reset()          # the core died
shell2.session.close()                # the shell saw the break
check("оболочка знает, что связи нет",
      shell2.session.state == SessionState.CLOSED)

core3 = ReferenceCore(store=store)    # the shell raised the core afresh
shell3 = ReferenceShell()
handshake(shell3, core3)
check("новое рукопожатие состоялось", shell3.session.ready)
answers = talk(shell3, core3, "settings.get", {})
values = one(answers, "ответ").payload["values"]
check("пользовательские данные пережили падение",
      values == {"голос": "Рина", "темп": 1.1}, f"| {values}")
check("летучее состояние не пережило",
      was["задачи"] == 1 and core3.volatile.snapshot()["задачи"] == 0)
check("и выданное разрешение тоже не пережило",
      core3.permissions.ledger.pending() == 0)

# --- 12 --------------------------------------------------------------------
requirement(12, "trace_id во всей цепочке от запроса до финального события")

chain = new_trace_id()
answers = talk(shell, core, "command.handle",
               {"text": "который час", "source": "typed"}, trace_id=chain)
traces = {m.trace_id for m in answers}
check("ответ и событие несут трассировку запроса", traces == {chain},
      f"| {sorted(traces)}")
check("в цепочке есть и ответ, и событие",
      {m.type for m in answers} == {MessageType.RESPONSE, MessageType.EVENT})

chain2 = new_trace_id()
answers = talk(shell, core, "command.handle",
               {"text": "усыпи компьютер", "source": "voice"},
               trace_id=chain2)
check("ошибка тоже несёт трассировку запроса",
      {m.trace_id for m in answers} == {chain2})


# ---------------------------------------------------------------------------
print()
print(f"Проверок: {checks}, ошибок: {fails}")
print(f"Побочные эффекты песочницы: запущено {len(box.launched)}, "
      f"открыто {len(box.opened)}, системных действий {len(box.actions)}")
sys.exit(1 if fails else 0)
