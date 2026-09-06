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

engine.say("готово")
_time.sleep(0.4)
check("синтез позвали на настоящий ответ", "готово" in voice.said,
      f"| {voice.said}")
# The round is closed: the recognised phrase reached the command pipeline,
# and Rina answered it herself — "Засекла 5 с." in the list of what was
# synthesised.
check("распознанное исполнилось, и ответ тоже озвучен",
      any("Засекла" in said for said in voice.said), f"| {voice.said}")
check("местный динамик при этом молчал", box.spoken == [], f"| {box.spoken}")

print()
print("ИТОГО ошибок:", fails)
sys.exit(1 if fails else 0)
