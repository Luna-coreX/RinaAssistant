# -*- coding: utf-8 -*-
"""
4.0-G: the chain from the microphone to a recognised phrase, joint by joint.

Three separate defects in this chain looked identical from outside — "she
cannot hear me" — and each broke at a different joint. The core opened its
own microphone and ignored the streamed sound; the shell never started
capture; the speaking flag latched true and left the microphone muted for
the rest of the session. Nothing anywhere said which joint it was, so the
first two were found by guessing, and the guesses were wrong.

What is checked is the **whole chain, one link at a time**: sound handed to
the core exactly as the data channel hands it, then the counters at each
stage. A check that only asserted the last link would say "not recognised"
and leave the same question standing.

The recogniser itself is not required. Whether a model is installed is the
person's business and differs between machines; whether the sound reaches
the recogniser is ours, and it is the same everywhere.
"""
import math
import os
import struct
import sys

sys.path.insert(0, r"C:\DevStation\PCDev\DesktopApps\RinaAssistant")

from core.speech import RATE, Segmenter

fails = 0


def check(label, cond, detail=""):
    global fails
    if not cond:
        fails += 1
    print(("OK   " if cond else "FAIL "), label, detail)


def sound(seconds, loudness=0.3):
    """A tone at a stated loudness — a stand-in for a voice."""
    frames = int(RATE * seconds)
    return struct.pack(
        f"<{frames}h",
        *(int(loudness * 32767 * math.sin(2 * math.pi * 220 * n / RATE))
          for n in range(frames)))


def silence(seconds):
    return b"\x00\x00" * int(RATE * seconds)


print("=== громкость: тишина и речь различимы ===")
quiet = Segmenter.level(silence(0.1))
loud = Segmenter.level(sound(0.1))
check("тишина ниже порога", quiet < 0.02, f"| {quiet:.4f}")
check("речь выше порога", loud >= 0.02, f"| {loud:.4f}")

# The threshold is the one number in this chain that a person's microphone
# can fall foul of without anything being broken. Naming the quietest sound
# that still counts turns "she cannot hear me" into a number one can check
# against one's own device.
faintest = None
for step in range(1, 40):
    if Segmenter.level(sound(0.1, step / 200)) >= 0.02:
        faintest = step / 200
        break
check("самый тихий слышимый звук назван", faintest is not None,
      f"| громкость {faintest} из 1.0")

print()
print("=== нарезка: фраза кончается вместе с молчанием ===")
cutter = Segmenter()
check("во время речи фраза не выдаётся", cutter.feed(sound(0.5)) == [])
check("и в короткой паузе тоже", cutter.feed(silence(0.3)) == [])
phrases = cutter.feed(silence(0.6))
check("после паузы длиннее порога — выдаётся", len(phrases) == 1,
      f"| {len(phrases)}")
if phrases:
    seconds = len(phrases[0]) / (RATE * 2)
    check("и в ней вся речь, а не хвост", seconds >= 0.5,
          f"| {seconds:.2f} с")

print()
print("=== слишком тихая речь не режется вовсе ===")
# Not a defect but the commonest cause: a quiet microphone means silence to
# the segmenter, and silence means no phrase, and no phrase means no error
# message either. Worth being able to point at.
whisper = Segmenter()
whisper.feed(sound(1.0, 0.005))
check("шёпот ниже порога фразы не даёт",
      whisper.feed(silence(1.0)) == [])

print()
print("=== счётчики ядра считают то, что произошло ===")
from core.engine import RinaEngine
from core.settings_api import MemorySettings
from core.wire.server import ProtocolServer

engine = RinaEngine(settings=MemorySettings({
    "stt_engine": "disabled", "custom_commands": [], "reminders": [],
    "history": [],
}))
class NoModel:
    """A recogniser with no model — the state a fresh machine is in."""

    @staticmethod
    def available():
        return False


server = ProtocolServer.__new__(ProtocolServer)
server.engine = engine
server.segmenter = Segmenter()
server.recogniser = NoModel()
server.heard = {"bytes": 0, "frames": 0, "loud_frames": 0, "phrases": 0,
                "recognitions": 0, "texts": 0}

server._hear(sound(0.5))
server._hear(silence(1.0))
seen = server.hearing()
check("байты посчитаны", seen["bytes"] > 0, f"| {seen['bytes']} Б")
check("громкие кадры отделены от тихих",
      0 < seen["loud_frames"] < seen["frames"],
      f"| громких {seen['loud_frames']} из {seen['frames']}")
check("фраза дошла до распознавания", seen["phrases"] == 1,
      f"| {seen['phrases']}")

print()
print("ИТОГО ошибок:", fails)

# `os._exit`, because recognition runs in daemon threads and one of them is
# still alive when the interpreter starts to shut down — it dies holding the
# lock on stderr and turns a green check into a fatal error. The same reason
# `test_settings_api.py` leaves this way.
sys.stdout.flush()
sys.stderr.flush()
os._exit(1 if fails else 0)
