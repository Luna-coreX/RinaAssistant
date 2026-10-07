# -*- coding: utf-8 -*-
"""
4.0b-D05: the beta's telemetry — nothing while it is off, words from a
vocabulary while it is on.

The promise it makes is short and each half can be broken silently:

    off     nothing is counted, nothing is kept, no connection is opened
    on      what leaves is numbers and known words; no phrase, no path,
            no name, and a plugin's tool leaves as `plugin`, unnamed

The first is asked with the network made to explode, of a core driven
through real commands. The second is asked of the report itself: not «is
the field there» but «is anything in it that a person said» — the report
must not hold a single Cyrillic letter, because every phrase this core
hears is Russian.

The collector is asked the same thing from its side: `validate` in
`server/telemetry/validate.js`, run by Node, must take the reports this core
really builds and refuse ones with a phrase, a name or a stranger's id in
them. Its two functions (`collector.js`) are driven with a store of the
test's own: a report is kept under the day it arrived, a spoiled or
oversized one is not, and the nightly clean-up answers only its secret.
Without Node that part is skipped, and says so.

And the path the shell takes is asked of a live core: switched on with
`settings.set`, counting a command, writing its counts down when the shell
goes, and forgetting them when it is switched off.

To run:
    python tools/test_telemetry.py
"""
import io
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sandbox import isolate_storage

isolate_storage()

from console import use_utf8

use_utf8()

from core import telemetry as tm
from core.engine import RinaEngine
from core.events import EventBus
from core.settings_api import MemorySettings
from core.settings_store import config_dir

fails = 0


def check(label, cond, detail=""):
    global fails
    if not cond:
        fails += 1
    print(("OK   " if cond else "FAIL "), label, detail)


# ---------------------------------------------------------------------------
# The network explodes for the whole in-process half
# ---------------------------------------------------------------------------
opened = []


def refuse(*args, **kwargs):
    opened.append(repr(args)[:80])
    raise OSError("сеть запрещена проверкой")


real_connect = socket.socket.connect
socket.socket.connect = lambda self, *args: refuse(*args)
socket.create_connection = refuse
urllib.request.urlopen = refuse

said = []


def core(**values):
    settings = MemorySettings({"custom_commands": [], "reminders": [],
                               "history": [], "todo": [], **values})
    engine = RinaEngine(settings=settings, event_bus=EventBus())
    engine.voice_out = lambda text, **kw: said.append(text)
    engine.browser_out = lambda url: (True, "")
    engine.launch_out = lambda path, kind: (True, "")
    engine.apps_source = lambda: [{"name": "Notepad", "launch": "notepad.exe",
                                   "kind": "file", "source": "start_menu"}]
    return settings, engine


COMMANDS = ["посчитай 17 умножить на 23", "открой блокнот",
            "запиши в дела купить хлеб", "что в делах"]

print("=== выключено — значит ничего ===")
settings, engine = core()
for phrase in COMMANDS:
    engine.handle_command(phrase)
engine.telemetry.flush()
kept = os.path.join(config_dir(), tm.FILE)
check("по умолчанию выключено", settings.get("telemetry") is False)
check("ничего не сосчитано и не записано", not os.path.exists(kept),
      f"| {kept}")
check("отчёта нет", engine.telemetry.report() is None)
# Somewhere to send, as there will be once the collector is deployed. With
# `ENDPOINT` still empty, «no connection» would hold for want of an
# address, whatever the switch said — measured by breaking the switch.
engine.telemetry._endpoint = "https://collector.test/v1/report"
check("отправка отвечает «выключено»", engine.telemetry.maybe_send(True) == "off")
check("и ни одного соединения", not opened, f"| {opened}")
engine.telemetry._endpoint = ""

print()
print("=== включено — только слова из словаря ===")
settings.set("telemetry", True)
for phrase in COMMANDS:
    engine.handle_command(phrase)
engine.telemetry.tool("plugin.private_diary.write", False, "disk_full",
                      "because")
# A tool name from a person's own command card (`4.0b-K01`): a Latin word
# typed into a file, not a name of the program's. Counted as `other`.
engine._tools.call_block("my_secret_project", {})
report = engine.telemetry.report()
text = json.dumps(report, ensure_ascii=False)
check("отчёт есть", isinstance(report, dict))
check("в нём ровно оговорённые поля",
      set(report) == {"schema", "install", "app", "os", "language", "days",
                      "engines", "features", "tools", "errors", "reasons",
                      "timings"}, f"| {sorted(report)}")

# What the consent window says leaves, field by field (audit 2026-10-07,
# L-5): the first edition named half of the report. A field added to the
# report without a word for it here goes red, and so does a word taken out
# of the window.
SAID_AS = {
    "schema": None,                       # the shape's number, not about you
    "install": "случайный номер установки",
    "app": "Версия программы",
    "os": "Windows",
    "language": "язык интерфейса",
    "days": "сколько дней идёт подсчёт",
    "features": "какие команды",
    "tools": "инструменты срабатывали",
    "errors": "коды ошибок",
    "reasons": "причины отказов",
    "timings": "время распознавания и первого звука",
    "engines.stt_engine": "движки распознавания",
    "engines.tts_engine": "озвучки",
    "engines.model": "ответы моделью",
    "engines.always_listen": "постоянное слушание",
    "engines.personality": "личность",
}
with io.open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "shell", "Rina.Shell", "Pages",
                          "TelemetryConsent.xaml.cs"), encoding="utf-8") as f:
    consent = f.read()
fields = ((set(report) - {"engines"})
          | {f"engines.{k}" for k in report["engines"]})
check("каждое поле отчёта названо в окне согласия",
      fields <= set(SAID_AS)
      and all(word is None or word in consent for word in SAID_AS.values()),
      f"| без слов: {sorted(fields - set(SAID_AS))}, нет в окне: "
      f"{[w for w in SAID_AS.values() if w and w not in consent]}")
check("и окно говорит, что адрес видит платформа",
      "IP-адрес" in consent and "Vercel" in consent)

check("намерения сосчитаны по каталогу",
      report["features"].get("calc") == 1
      and report["features"].get("app.launch") == 1, f"| {report['features']}")
check("в отчёте нет ни одной буквы из сказанного",
      not re.search(r"[А-Яа-яЁё]", text), f"| {text[:200]}")
check("и ни одного слова вне словаря",
      all(re.match(r"^[a-z][a-z0-9_.:]*$", word)
          for group in ("features", "tools", "errors", "reasons")
          for word in report[group]), f"| {text[:200]}")
check("имя из карточки команды не уходит — только `other`",
      "my_secret_project" not in text and report["tools"].get("other"),
      f"| {report['tools']}")
check("чужой плагин уходит безымянным",
      "private_diary" not in text and "disk_full" not in text
      and report["tools"].get("plugin") == 1, f"| {report['tools']}")
check("и ни одного соединения, пока некуда слать",
      engine.telemetry.maybe_send(True) == "no_endpoint" and not opened,
      f"| {opened}")

print()
print("=== отправка ===")
folder = tempfile.mkdtemp()
posted = []
answers = [False, True]
sender = tm.Telemetry(settings, folder=folder, endpoint="https://example.invalid/r",
                      post=lambda url, body: (posted.append(body),
                                              answers.pop(0))[1])
sender.intent("calc")
sender.timing("recognition", 0.61)
install = sender.report()["install"]
plain = tm.Telemetry(settings, folder=folder, endpoint="http://example.invalid/r",
                     post=lambda url, body: posted.append(body) or True)
check("по http отчёт не уходит вовсе",
      plain.maybe_send(True) == "insecure" and not posted, f"| {posted}")
check("сервер не принял — счёт ждёт", sender.maybe_send(True) == "failed"
      and sender.report()["features"].get("calc") == 1)
check("принял — отправлено", sender.maybe_send(True) == "sent", f"| {posted[-1:]}")
check("что ушло, то и видно человеку",
      sender.sent() and sender.sent()[-1]["report"] == posted[-1])
check("и сосчитанное не уйдёт второй раз",
      not sender.report()["features"] and not sender.report()["timings"])
check("а назавтра, не раньше", sender.maybe_send() == "not_due")
check("идентификатор тот же, пока включено",
      sender.report()["install"] == install)

print()
print("=== выключили — забыто ===")
sender.forget()
check("накопленное удалено", not os.path.exists(os.path.join(folder, tm.FILE)))
check("а запись отправленного осталась у человека", len(sender.sent()) == 1)
check("включили снова — это уже кто-то новый",
      sender.report()["install"] != install)
shutil.rmtree(folder, ignore_errors=True)

# ---------------------------------------------------------------------------
# Nor does anything else knock on its own
# ---------------------------------------------------------------------------
#
# D05 is done when, with telemetry off, the program makes no request the
# person did not make. Whisper made one on every load: given a size,
# faster-whisper asks huggingface.co for the latest revision and falls back
# to the cache only when that fails — so on a machine with the model long
# downloaded, and the network up, every start of recognition went out.
print()
print("=== и без телеметрии ядро само в сеть не ходит ===")
import faster_whisper
from faster_whisper.utils import download_model

from core.speech import FasterWhisperRecogniser

asked = []


class Recorded:
    """The model class, as far as where it was told to load from."""
    cached = True

    def __init__(self, size, **kwargs):
        asked.append(kwargs.get("local_files_only", False))
        if kwargs.get("local_files_only") and not Recorded.cached:
            raise FileNotFoundError("not in the cache")


real_model = faster_whisper.WhisperModel
faster_whisper.WhisperModel = Recorded
check("скачанная модель грузится с диска, без вопроса к huggingface.co",
      FasterWhisperRecogniser("base")._load() and asked == [True], f"| {asked}")
del asked[:]
Recorded.cached = False
check("нескачанная — скачивается: это человек выбрал в мастере",
      FasterWhisperRecogniser("base")._load() and asked == [True, False],
      f"| {asked}")
faster_whisper.WhisperModel = real_model

# And the library itself, where the model is on this disk: the flag is
# worth something only if faster-whisper honours it. Asking the cache
# alone makes no request.
try:
    download_model("base", local_files_only=True)
    on_disk = True
except (FileNotFoundError, ValueError):
    on_disk = False
if not on_disk:
    print("     пропущено: модели base на этом диске нет — библиотека не проверена")
else:
    del opened[:]
    check("настоящая библиотека грузит скачанную модель без сети",
          FasterWhisperRecogniser("base")._load() and opened == [],
          f"| попытки соединения: {opened}")

socket.socket.connect = real_connect

# ---------------------------------------------------------------------------
# The collector takes what the core sends, and nothing else
# ---------------------------------------------------------------------------
print()
print("=== сборщик принимает отчёт ядра — и ничего другого ===")


def spoiled(change):
    copy = json.loads(json.dumps(posted[-1]))
    change(copy)
    return copy


collector_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             "server", "telemetry")


def module_url(name):
    return json.dumps("file:///" + os.path.join(collector_dir, name).replace(os.sep, "/"))
tampered = [
    ("лишнее поле с текстом", spoiled(lambda r: r.update(text="запусти стим"))),
    ("слово не из словаря", spoiled(lambda r: r["features"].update({"запусти": 1}))),
    ("имя компьютера в поле ОС",
     spoiled(lambda r: r.update(os="Windows 11 Pro (DESKTOP-HOME)"))),
    ("счёт меньше нуля", spoiled(lambda r: r["tools"].update(launch_app=-3))),
    ("чужой идентификатор", spoiled(lambda r: r.update(install="user@example.com"))),
]
scratch = tempfile.mkdtemp()
runner = os.path.join(scratch, "run.mjs")
listed = os.path.join(scratch, "reports.json")
io.open(runner, "w", encoding="utf-8").write("\n".join((
    "import { validate } from %s;" % module_url("validate.js"),
    "import { readFileSync } from 'node:fs';",
    "const reports = JSON.parse(readFileSync(process.argv[2], 'utf8'));",
    "console.log(JSON.stringify(reports.map(validate)));",
    "")))
io.open(listed, "w", encoding="utf-8").write(json.dumps(
    [report, posted[-1]] + [one for _label, one in tampered], ensure_ascii=False))
try:
    ran = subprocess.run(["node", runner, listed], capture_output=True,
                         text=True, encoding="utf-8", timeout=60)
    verdicts = json.loads(ran.stdout) if ran.returncode == 0 else None
    trouble = ran.stderr.strip()[-300:]
except (OSError, ValueError, subprocess.TimeoutExpired) as failed:
    verdicts, trouble = None, str(failed)
shutil.rmtree(scratch, ignore_errors=True)
if verdicts is None:
    # A machine without Node cannot ask the collector; that is said aloud
    # rather than counted as a pass or a failure of the program.
    print("     пропущено: node не запустился — сборщик не проверен |", trouble)
else:
    check("отчёт, который строит ядро, принимается",
          verdicts[0] == "" and verdicts[1] == "", f"| {verdicts[:2]}")
    for (label, _one), verdict in zip(tampered, verdicts[2:]):
        check(f"отклоняется: {label}", verdict != "", f"| {verdict!r}")

# The collector's two functions, with a store that only writes down what it
# was asked. The clock is fixed, so the days are known here in advance.
import datetime

print()
print("=== сборщик: что хранит и кого пускает чистить ===")
NOW = datetime.datetime(2026, 10, 1, 12, 0, tzinfo=datetime.timezone.utc)
CUTOFF = (NOW - datetime.timedelta(days=180)).date().isoformat()
scratch = tempfile.mkdtemp()
runner = os.path.join(scratch, "collect.mjs")
io.open(runner, "w", encoding="utf-8").write("\n".join((
    "import { receive, clean } from %s;" % module_url("collector.js"),
    "import { readFileSync } from 'node:fs';",
    "const report = readFileSync(process.argv[2], 'utf8');",
    "const now = %d;" % int(NOW.timestamp() * 1000),
    "const asked = [];",
    "const store = {",
    "  keep: async (...args) => { asked.push(['keep', ...args]); },",
    "  dropBefore: async (...args) => { asked.push(['dropBefore', ...args]); },",
    "};",
    "const post = (body) => new Request('https://c.test/api/v1/report', { method: 'POST', body });",
    "const get = (auth) => new Request('https://c.test/api/clean',",
    "  auth === null ? {} : { headers: { authorization: auth } });",
    "const out = {};",
    # A thunk, not a promise: the call must start after `before` is taken,
    # or a store call made before its first `await` is missed.
    "async function run(name, call) {",
    "  const before = asked.length;",
    "  const response = await call();",
    "  out[name] = { status: response.status, body: await response.text(),",
    "                asked: asked.slice(before) };",
    "}",
    "const spoiled = JSON.parse(report); spoiled.text = 'запусти стим';",
    "await run('valid', () => receive(post(report), store, now));",
    "await run('spoiled', () => receive(post(JSON.stringify(spoiled)), store, now));",
    "await run('broken', () => receive(post('{not json'), store, now));",
    "await run('huge', () => receive(post('x'.repeat(17 * 1024)), store, now));",
    "await run('clean_none', () => clean(get(null), store, 's3cret-s3cret-s3', now));",
    "await run('clean_wrong', () => clean(get('Bearer nope'), store, 's3cret-s3cret-s3', now));",
    "await run('clean_unset', () => clean(get('Bearer '), store, '', now));",
    "await run('clean_right', () => clean(get('Bearer s3cret-s3cret-s3'), store, 's3cret-s3cret-s3', now));",
    "console.log(JSON.stringify(out));",
    "")))
listed = os.path.join(scratch, "report.json")
io.open(listed, "w", encoding="utf-8").write(json.dumps(posted[-1], ensure_ascii=False))
try:
    ran = subprocess.run(["node", runner, listed], capture_output=True,
                         text=True, encoding="utf-8", timeout=60)
    seen = json.loads(ran.stdout) if ran.returncode == 0 else None
    trouble = ran.stderr.strip()[-300:]
except (OSError, ValueError, subprocess.TimeoutExpired) as failed:
    seen, trouble = None, str(failed)
shutil.rmtree(scratch, ignore_errors=True)
if seen is None:
    print("     пропущено: node не запустился — сборщик не проверен |", trouble)
else:
    kept = seen["valid"]["asked"]
    check("отчёт ядра принят", seen["valid"]["status"] == 204, f"| {seen['valid']}")
    check("и сохранён один раз, под днём получения и своей установкой",
          len(kept) == 1 and kept[0][:3] == ["keep", NOW.date().isoformat(),
                                             posted[-1]["install"]],
          f"| {kept}")
    check("сохранён тот же отчёт, без добавлений",
          len(kept) == 1 and json.loads(kept[0][3]) == posted[-1])
    for name, label, status in (("spoiled", "испорченный", 400),
                                ("broken", "не JSON", 400),
                                ("huge", "больше предела", 413)):
        check(f"{label} — отказ {status} и ничего не сохранено",
              seen[name]["status"] == status and not seen[name]["asked"],
              f"| {seen[name]}")
    for name, label in (("clean_none", "без секрета"),
                        ("clean_wrong", "с чужим секретом"),
                        ("clean_unset", "пока секрет не задан")):
        check(f"чистка {label} — 401, база не тронута",
              seen[name]["status"] == 401 and not seen[name]["asked"],
              f"| {seen[name]}")
    check("чистка со своим секретом удаляет старше 180 дней",
          seen["clean_right"]["status"] == 204
          and seen["clean_right"]["asked"] == [["dropBefore", CUTOFF]],
          f"| {seen['clean_right']}")

# ---------------------------------------------------------------------------
# The path the shell takes, through a live core
# ---------------------------------------------------------------------------
print()
print("=== настоящее ядро: включить, сосчитать, забыть ===")
from coreproc import Core


def answer(live, method, payload=None):
    sent = live.ask(method, payload or {})
    for _ in range(12):
        got = live.read(1, timeout=15.0)
        if not got:
            break
        if got[0].correlation_id == sent.id:
            return got[0].payload
    return {}


home = tempfile.mkdtemp()
file = os.path.join(home, "RinaAssistant", tm.FILE)
try:
    live = Core(env={"APPDATA": home, "XDG_CONFIG_HOME": home})
    live.handshake()
    on = answer(live, "settings.set", {"values": {"telemetry": True}})
    check("включается настройкой",
          (on.get("results") or on.get("verdicts") or {}).get("telemetry", {})
          .get("accepted") is not False, f"| {on}")
    live.ask("command.handle", {"text": "посчитай 6 умножить на 7",
                                "source": "typed", "require_wake": False})
    # The intent is counted as soon as the command is understood, before
    # the person's line goes into the history — so the history changing is
    # the moment the count exists. Her answer is not waited for: it goes
    # through speech and plugins, which are not what is asked here.
    heard = live.read_until("history.changed", timeout=60.0)
    check("ядро приняло команду",
          any(m.method == "history.changed" for m in heard),
          f"| {[m.method or m.type for m in heard]}")
    live.proc.stdin.close()
    live.wait()
    counted = {}
    if os.path.exists(file):
        counted = json.load(io.open(file, encoding="utf-8"))
    check("уходя, ядро записало сосчитанное",
          counted.get("features", {}).get("calc") == 1, f"| {counted}")

    live = Core(env={"APPDATA": home, "XDG_CONFIG_HOME": home})
    live.handshake()
    answer(live, "settings.set", {"values": {"telemetry": False}})
    # Forgotten inside `settings.set`, before the answer: asked right after
    # it rather than after the core has gone.
    check("выключили — файла с накопленным нет",
          counted and not os.path.exists(file), f"| {file}")
    live.proc.kill()
    live.wait()
finally:
    shutil.rmtree(home, ignore_errors=True)

print()
print("ИТОГО ошибок:", fails)
sys.stdout.flush()
os._exit(1 if fails else 0)
