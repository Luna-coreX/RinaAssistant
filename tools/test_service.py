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
            if self.proc.poll() is not None:
                break                # ядро умерло — ждать больше нечего
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
check("и что перезапуск обязателен",
      schema["ui_language"]["restart_required"] is True)
check("и что ключ служебный", schema["first_run"]["secret"] is True)
check("раскладку ядро не описывает намеренно",
      described.payload.get("layout") is None
      and "ADR 0006" in described.payload.get("note", ""),
      f"| {described.payload.get('note')}")

# Запись: вердикт по каждому ключу, а не одно «получилось» на всю посылку.
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

# Первый настоящий потребитель канала событий: до сих пор его проверяли
# заглушками. Напоминание ставится голосовой командой — через настоящий
# разбор, — и приходит push-событием, которого никто не запрашивал.
timer = Core()
timer.handshake()

timer.ask("command.handle", {"text": "засеки 3 секунды", "source": "voice"})
booked = timer.read_until("assistant.response", timeout=20)
check("команда принята и подтверждена вслух",
      any(m.method == "assistant.response" for m in booked),
      f"| {[m.method for m in booked]}")

# Ответ на список и само срабатывание идут по одному каналу и могут
# перемешаться: таймер трёхсекундный, а ответ приходит когда приходит.
# Поэтому читается один поток до срабатывания, а разбирается он потом.
# Первая редакция этой проверки ждала их по очереди — и цикл ожидания
# ответа съедал пришедшее следом событие, после чего второй цикл ждал
# того, что уже прочитано.
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


# ---------------------------------------------------------------------------
print()
print("=== F04: команды и история через протокол ===")

# Шесть возможностей инвентаря были недостижимы: место в архитектуре у них
# было, а метода не было. Здесь проверяется, что теперь достижимы.
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

# История: разговор виден, стирается и выгружается.
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

# Установка плагина честно отвечает «ещё нет», а не молчит.
work.ask("plugins.install", {"source": "C:/nowhere"})
answer = work.read(1)[0]
check("установка плагина отвечает честным отказом",
      answer.type == MessageType.ERROR and "H" in answer.payload["message"],
      f"| {answer.payload.get('message')}")

work.ask("core.shutdown")
work.read(1)
work.wait()

print()
print("ИТОГО ошибок:", fails)
sys.exit(1 if fails else 0)
