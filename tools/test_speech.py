# -*- coding: utf-8 -*-
"""
E03, E04: распознавание и синтез в ядре, звук — в оболочке.

Настоящие модели ставятся не на всякой машине, а провод обязан проверяться
везде. Поэтому распознавание и синтез подменяются: их **границы** узкие
(байты → текст, текст → байты) ровно для того, чтобы это было возможно.
Проверяется путь, а не модель.

Нарезка на фразы проверяется по-настоящему: это наш код, и он не зависит ни
от какой библиотеки.

Запуск:
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

# Пауза между словами не рвёт фразу — иначе «поставь… таймер» приедет двумя,
# и вторая половина придёт без первой.
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
    """Подмена: важно, что путь дошёл, а не что услышано."""

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
    """Подмена: отдаёт тон вместо голоса, чтобы было что отправить."""

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

# Звук приходит так же, как от оболочки: кусками по сто миллисекунд.
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

# Ответ Рины уходит звуком в оболочку, а не в местный динамик.
server.data.open_stream(21, "audio.output")
server.data.grant(21, 512 * 1024)
server._speech_stream = 21
server.send_speech(speech.tone(0.3), speech.RATE)

# Байты ушли в трубу оболочки — читаем её так же, как читала бы оболочка.
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
# Круг замкнулся: распознанная фраза дошла до конвейера команд, и Рина
# ответила на неё сама — «Засекла 5 с.» в списке синтезированного.
check("распознанное исполнилось, и ответ тоже озвучен",
      any("Засекла" in said for said in voice.said), f"| {voice.said}")
check("местный динамик при этом молчал", box.spoken == [], f"| {box.spoken}")

print()
print("ИТОГО ошибок:", fails)
sys.exit(1 if fails else 0)
