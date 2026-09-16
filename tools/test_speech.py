# -*- coding: utf-8 -*-
"""
E03, E04: recognition and synthesis in the core, the sound in the shell.

Real models are not installed on every machine, and the wire is obliged to
be checked everywhere. So recognition and synthesis are substituted: their
**boundaries** are narrow (bytes -> text, text -> bytes) precisely so that
this is possible. The path is checked, not the model.

The slicing into phrases is checked for real: it is our code, and it depends
on no library.

To run:
    python tools/test_speech.py
"""

import io
import os
import sys

from console import use_utf8

use_utf8()

ROOT = r"C:\DevStation\PCDev\DesktopApps\RinaAssistant"
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
os.chdir(ROOT)

from sandbox import neutralise
box = neutralise()

from core import speech
from core.engine import RinaEngine
from core.events import EventBus
from core.wire.envelope import FrameDecoder
from core.wire.server import ProtocolServer
from core.wire.transport import Channels, InProcessTransport

fails = 0


def check(label, cond, detail=""):
    global fails
    if not cond:
        fails += 1
    print(("OK   " if cond else "FAIL "), label, detail)


# ---------------------------------------------------------------------------
print("=== E03: нарезка на фразы ===")

CHUNK = int(speech.RATE * 0.1) * 2


def cut(stream, segmenter=None):
    segmenter = segmenter or speech.Segmenter()
    got = []
    for at in range(0, len(stream), CHUNK):
        got += segmenter.feed(stream[at:at + CHUNK])
    return got, segmenter


phrases, _ = cut(speech.tone(0.6) + speech.silence(1.0))
check("фраза кончается по тишине", len(phrases) == 1, f"| {len(phrases)}")

# A pause between words does not tear a phrase — otherwise "поставь… таймер"
# arrives as two, and the second half comes without the first.
phrases, _ = cut(speech.tone(0.5) + speech.silence(0.3)
                 + speech.tone(0.4) + speech.silence(1.0))
check("пауза между словами не рвёт фразу", len(phrases) == 1,
      f"| {len(phrases)}")
check("фраза целая, вместе с паузой внутри",
      phrases and abs(len(phrases[0]) / (speech.RATE * 2) - 1.9) < 0.2,
      f"| {len(phrases[0]) / (speech.RATE * 2):.2f} с" if phrases else "")

phrases, _ = cut(speech.silence(3.0))
check("тишина фраз не рождает", not phrases)

phrases, _ = cut(speech.tone(0.1) + speech.silence(1.0))
check("слишком короткий звук не считается фразой", not phrases,
      "| щелчок или хлопок дверью")

phrases, _ = cut(speech.tone(0.5) + speech.silence(1.0)
                 + speech.tone(0.5) + speech.silence(1.0))
check("две фразы приходят порознь", len(phrases) == 2, f"| {len(phrases)}")

long_speech, _ = cut(speech.tone(25.0))
check("бесконечная речь всё же кончается", len(long_speech) >= 1,
      "| микрофон у работающего телевизора")

print(f"     уровень: тон {speech.Segmenter.level(speech.tone(0.1)):.3f}, "
      f"тишина {speech.Segmenter.level(speech.silence(0.1)):.3f}")


# ---------------------------------------------------------------------------
print()
print("=== E03: распознавание без модели говорит прямо ===")

quiet = speech.DisabledRecogniser()
check("недоступность объявлена", not quiet.available())
heard = quiet.recognise(speech.tone(1.0))
check("отказ, а не молчание", not heard.ok and heard.error == "stt.unavailable",
      f"| {heard}")


# ---------------------------------------------------------------------------
print()
print("=== E03: чужая папка отвергается там, где её выбирают ===")

# From a person's journal. They went to the Vosk download page and brought
# back `vosk-recasepunc-ru-0.22`, which is on that page and is not a
# recognition model but a restorer of case and punctuation. Everything
# looked right — the folder was there, the package was there, the setting
# pointed at it — and every phrase ended in `Failed to create a model`:
# the library's words, in English, in the journal only, once per phrase.
# Four days of "she cannot hear me".
#
# The verdict belongs where the choosing happens. The settings already
# show why an engine cannot be picked; it simply had nothing to show,
# because the folder was only ever opened at the first phrase.

import tempfile

sham = os.path.join(tempfile.mkdtemp(prefix="rina-model-"), "recasepunc")
os.makedirs(sham)
for near in ("checkpoint", "example.py", "README"):
    io.open(os.path.join(sham, near), "w", encoding="utf-8").write("x")

check("подделка не принимается за модель",
      not speech.looks_like_vosk_model(sham), f"| {sorted(os.listdir(sham))}")

real = os.path.join(tempfile.mkdtemp(prefix="rina-model-"), "vosk-ru")
for part in ("am", "conf", "graph", "ivector"):
    os.makedirs(os.path.join(real, part))
check("настоящая — принимается", speech.looks_like_vosk_model(real),
      f"| {sorted(os.listdir(real))}")

# And one folder at a time is enough: small models, large ones and the ones
# with a dynamic graph differ in what else they carry, and demanding all
# four would turn away models that work.
half = os.path.join(tempfile.mkdtemp(prefix="rina-model-"), "vosk-small")
os.makedirs(os.path.join(half, "conf"))
check("одной приметы довольно", speech.looks_like_vosk_model(half))

wrong = speech.VoskRecogniser(sham)
check("движок с такой папкой недоступен", not wrong.available())
check("и причина названа человеческими словами",
      "не модель распознавания" in getattr(wrong, "_error", ""),
      f"| {getattr(wrong, '_error', '')!r}")

# The reason has to reach the place a person is looking at, not stay in the
# object. This is the list the settings page draws.
from core import settings_schema
from core.settings_api import MemorySettings

listed = settings_schema.options_for(
    "stt_engine", MemorySettings({"stt_engine": "vosk", "vosk_model": sham}))
vosk_row = [row for row in listed if row["value"] == "vosk"]
check("в настройках движок показан недоступным",
      bool(vosk_row) and not vosk_row[0]["available"],
      f"| {vosk_row}")
check("и там же написано почему",
      bool(vosk_row) and "модел" in (vosk_row[0].get("reason") or ""),
      f"| {vosk_row[0].get('reason') if vosk_row else None!r}")


# ---------------------------------------------------------------------------
print()
print("=== E03/E04: путь через провод ===")


class FakeRecogniser:
    """A stand-in: what matters is that the path arrived, not what was heard."""

    name = "подменённое"

    def __init__(self, text="поставь таймер на 5 секунд"):
        self.text = text
        self.calls = []

    def available(self):
        return True

    def recognise(self, pcm, language="ru"):
        self.calls.append(len(pcm))
        return speech.Heard(text=self.text)


class FakeSynthesiser:
    """A stand-in: gives out a tone instead of a voice, so there is something to send."""

    name = "подменённое"
    sample_rate = speech.RATE

    def __init__(self):
        self.said = []

    def available(self):
        return True

    def synthesize(self, text, voice="", rate=100):
        self.said.append(text)
        return speech.tone(0.4)


shell_control, core_control = InProcessTransport.pair()
shell_data, core_data = InProcessTransport.pair()

engine = RinaEngine(event_bus=EventBus())
ears = FakeRecogniser()
voice = FakeSynthesiser()
server = ProtocolServer(engine, Channels(core_control, core_data),
                        recogniser=ears, synthesiser=voice)

check("голос ядра забрала серверная сторона", engine.voice_out is not None)

heard_events = []
engine.bus.on("speech.recognized", lambda data: heard_events.append(data["text"]))

# The sound arrives the same way as from the shell: in hundred-millisecond chunks.
server.incoming[11] = {"kind": "audio.input", "format": {}, "bytes": 0,
                       "frames": 0}
stream = speech.tone(0.8) + speech.silence(1.2)
for at in range(0, len(stream), CHUNK):
    server._hear(stream[at:at + CHUNK])

import time as _time
for _ in range(50):
    if heard_events:
        break
    _time.sleep(0.05)

check("фраза дошла до распознавания", ears.calls, f"| {ears.calls}")
check("распознанное объявлено событием",
      heard_events == ["поставь таймер на 5 секунд"], f"| {heard_events}")

# Rina's answer goes to the shell as sound rather than to a local speaker.
server.data.open_stream(21, "audio.output")
server.data.grant(21, 512 * 1024)
server._speech_stream = 21
server.send_speech(speech.tone(0.3), speech.RATE)

# The bytes went into the shell's pipe — we read it as the shell would.
chunks = []
while True:
    piece = shell_data.recv()
    if not piece:
        break
    chunks.append(piece)
check("речь ушла оболочкой по каналу данных", chunks,
      f"| кусков {len(chunks)}")

def until(ready, seconds=8.0):
    """
    Wait for something to become true, up to a deadline.

    Instead of a fixed pause. A pause is a guess about how long a machine
    takes, and it is wrong in both directions: too long and every run pays
    for it, too short and the check reddens because something else was
    building at the time. This check went red only under the load of the
    full regression and green on its own — four times before it was worth
    tracing rather than re-running.
    """
    edge = _time.monotonic() + seconds
    while _time.monotonic() < edge and not ready():
        _time.sleep(0.02)
    return ready()


engine.say("готово")
until(lambda: "готово" in voice.said)
check("синтез позвали на настоящий ответ", "готово" in voice.said,
      f"| {voice.said}")
# The round is closed: the recognised phrase reached the command pipeline,
# and Rina answered it herself — "Засекла 5 с." in the list of what was
# synthesised.
until(lambda: any("Засекла" in said for said in voice.said))
check("распознанное исполнилось, и ответ тоже озвучен",
      any("Засекла" in said for said in voice.said), f"| {voice.said}")
check("местный динамик при этом молчал", box.spoken == [], f"| {box.spoken}")


print()
print("=== E04: длинная реплика уходит целиком ===")
# **What a person heard as "her speech glitches sometimes".** Sending
# used to `break` when the credit ran short, that is, throw away the rest
# of the reply. The initial self-issued credit is 32 KB — two thirds of a
# second of sound — and the loop runs through in microseconds, long
# before the shell could return credit for what it had played. Short
# replies fitted the window, long ones were cut, and neither journal had
# a line about it.
#
# The shell here is an imitation, but it behaves like the real one in the
# single thing that matters: it returns credit **as it plays**, not at
# once. A receiver that pays instantly is exactly the check that would
# stay green with the defect in place.
import threading

from core.wire.data import DataSender
from core.wire.envelope import Envelope


class Ids:
    def __init__(self):
        self.n = 0

    def next(self):
        self.n += 1
        return str(self.n)


class Playing:
    """An imitation shell that plays: takes bytes and pays for them after."""

    def __init__(self, server, pipe):
        self.server = server
        self.pipe = pipe
        self.taken = 0
        self.stop = False

    def start(self):
        thread = threading.Thread(target=self._play, daemon=True)
        thread.start()
        return self

    def _play(self):
        while not self.stop:
            piece = self.pipe.recv()
            if not piece:
                _time.sleep(0.005)
                continue
            self.taken += len(piece)
            # Played — so the credit for it goes back, the way
            # `AudioLink.ReadAsync` returns it after `RoomAsync`.
            _time.sleep(0.005)
            self.server._stream_credit(Envelope.request(
                "stream.credit", {"stream_id": 21, "bytes": len(piece)},
                id="c"))


def speaker(wait=None):
    """A bare server that can only send sound — and the pipe to listen on."""
    heard_side, core_side = InProcessTransport.pair()
    made = ProtocolServer.__new__(ProtocolServer)
    made.channels = Channels(None, core_side)
    made.data = DataSender()
    made.ids = Ids()
    made.send = lambda envelope: None
    made._speech_stream = 0
    made._speech_rate = 0
    made._speech_queue = None
    made._speech_sender = None
    made._running = True
    if wait is not None:
        made.SPEECH_WAIT = wait
    return made, heard_side


reply = speech.tone(4.0, rate=24000)          # four times the first window

long_server, long_pipe = speaker()
player = Playing(long_server, long_pipe).start()
long_server.send_speech(reply, 24000)
until(lambda: player.taken >= len(reply), seconds=25.0)
player.stop = True

check("вся реплика ушла к оболочке",
      long_server.data._credit[21].sent == len(reply),
      f"| отправлено {long_server.data._credit[21].sent} из {len(reply)} Б "
      f"({len(reply) / 48000:.1f} с звука)")
check("и оболочка приняла столько же", player.taken >= len(reply),
      f"| принято {player.taken} Б")

print()
print("=== E04: а если оболочка замолчала — сказано вслух ===")
# The other half of the same rule. Waiting for ever is no improvement on
# cutting off: a shell that has stopped playing must not hold a reply in
# the core until the end of time. What must not happen is the silence
# about it — so the cut is a warning in the journal, not a `break`.
deaf, _deaf_pipe = speaker(wait=0.3)         # nobody takes it and nobody pays
began = _time.monotonic()
deaf.send_speech(reply, 24000)
until(lambda: 21 in deaf.data.open
      and deaf.data._credit[21].sent >= 32 * 1024, seconds=5.0)
_time.sleep(0.6)          # longer than the wait for credit is allowed
spent = _time.monotonic() - began
check("не ждёт вечно", spent < 3.0, f"| остановилась через {spent:.1f} с")
check("и отправила ровно то, на что был кредит",
      deaf.data._credit[21].sent == 32 * 1024,
      f"| {deaf.data._credit[21].sent} Б")

print()
print("ИТОГО ошибок:", fails)
sys.exit(1 if fails else 0)
