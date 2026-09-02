# -*- coding: utf-8 -*-
"""
E01 + E02: ядро отдельным процессом, и с ним разговаривают по проводу.

Это первая проверка, где разделение не изображается, а происходит: ядро
запускается настоящим `subprocess`, у него свой интерпретатор, своя память и
свой журнал, а связь — только байты через стандартный ввод-вывод.

Ядро поднимается через `tools/_core_sandboxed.py`, а не напрямую: побочные
эффекты обезвреживаются в самом дочернем процессе, потому что песочница
родителя на него не распространяется.

Запуск:
    python tools/test_service.py
"""

import os
import subprocess
import sys
import time

ROOT = r"C:\DevStation\PCDev\DesktopApps\RinaAssistant"
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from core.wire import (Envelope, FrameDecoder, IdGenerator, MessageType,
                       Session, Side, encode_frame, new_trace_id)

fails = 0


def check(label, cond, detail=""):
    global fails
    if not cond:
        fails += 1
    print(("OK   " if cond else "FAIL "), label, detail)


LAUNCHER = os.path.join(ROOT, "tools", "_core_sandboxed.py")


class Core:
    """Ядро в отдельном процессе; наружу — только кадры."""

    def __init__(self, extra=()):
        self.proc = subprocess.Popen(
            [sys.executable, "-u", LAUNCHER, "--transport", "stdio", *extra],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, cwd=ROOT)
        self.decoder = FrameDecoder()
        self.ids = IdGenerator("s-")
        self.session = Session(side=Side.SHELL)

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
        Читать, пока не придёт нужное событие.

        Ответ «принято» и сам ответ Рины разделены во времени — в этом и
        смысл: команда думает, а запрос не держат открытым. Ждать
        фиксированное число сообщений значило бы гадать, сколько их будет.
        """
        seen = []
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline and len(seen) < limit:
            batch = self.read(1, timeout=deadline - time.monotonic())
            if not batch:
                break
            seen.extend(batch)
            if any(m.method == method for m in batch):
                break
        return seen

    def read(self, count=1, timeout=15.0):
        """Дождаться указанного числа сообщений."""
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
            got.extend(self.decoder.feed(header + body))
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
    capture_output=True, text=True, cwd=ROOT, encoding="utf-8")
check("ядро отвечает о себе и выходит с нулём", probe.returncode == 0)
check("объявляет версию протокола", "protocol_versions: 1" in probe.stdout)
check("объявляет возможности",
      "stt" in probe.stdout and "reminders" in probe.stdout,
      f"| {probe.stdout.strip().splitlines()[-1:]}")

bad = subprocess.run(
    [sys.executable, "-u", os.path.join(ROOT, "rina_core.py"),
     "--transport", "pipe"],
    capture_output=True, text=True, cwd=ROOT, encoding="utf-8")
check("без сессии режим pipe отклонён с кодом 2", bad.returncode == 2,
      f"| код {bad.returncode}")

# Ядро обязано работать там, где интерфейсной библиотеки нет.
headless = subprocess.run(
    [sys.executable, "-u", "-c",
     "import sys; sys.path.insert(0, r'%s');"
     "import rina_core, core.engine, core.wire.server;"
     "print('PySide6' in sys.modules)" % ROOT],
    capture_output=True, text=True, cwd=ROOT, encoding="utf-8")
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

core.ask("settings.describe")
described = core.read(1)[0]
check("схема настроек отдана", "schema" in described.payload)
check("раскладка честно не описана",
      described.payload.get("layout") is None
      and "E06a" in described.payload.get("note", ""),
      f"| {described.payload.get('note')}")

core.ask("core.shutdown")
core.read(1)
code = core.wait()
check("по просьбе ядро завершилось с нулём", code == 0, f"| код {code}")


# ---------------------------------------------------------------------------
print()
print("=== E01: ядро не переживает свою оболочку ===")

orphan = Core()
orphan.handshake()
check("ядро живо, пока канал открыт", orphan.proc.poll() is None)
orphan.proc.stdin.close()                      # «оболочка умерла»
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

print()
print("ИТОГО ошибок:", fails)
sys.exit(1 if fails else 0)
