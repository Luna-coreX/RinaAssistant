# -*- coding: utf-8 -*-
"""
4.0-G: the shell holds the microphone, not the core.

A check of its own, because the failure was not that a path was broken but
that **the wrong path was working**. The shell sent sound and the core piled
it into the segmenter — while opening its own microphone and parsing an
entirely different stream. Both paths were alive, the declared one was
unused, and from outside it looked like "she cannot hear": the device taken
twice, and what was recognised was whatever the core heard by itself.

What is checked is behaviour, not a device. No real microphone is needed
here and one would be harmful — the check is obliged to give the same answer
on a machine without one.
"""
import os
import sys

sys.path.insert(0, r"C:\DevStation\PCDev\DesktopApps\RinaAssistant")
sys.path.insert(0, os.path.join(
    r"C:\DevStation\PCDev\DesktopApps\RinaAssistant", "tools"))

# The checks do not touch the machine (`4.0-I04`).
#
# Under the interpreter the core actually runs on, `sounddevice` is
# installed — so every answer here played a real cue through the real
# speakers, sixty-nine of them across the suite, and two tests brought
# the process down on the way out. The group "машина" exists precisely
# so that the ordinary run touches nothing; this check belongs to the
# ordinary run.
#
# Storage is left alone: these tests bring their own, and moving it
# would change what they measure rather than what they touch.
from sandbox import neutralise

neutralise(storage=False)

from core.engine import RinaEngine
from core.settings_api import MemorySettings

fails = 0


def check(label, cond, detail=""):
    global fails
    if not cond:
        fails += 1
    print(("OK   " if cond else "FAIL "), label, detail)


class Watcher(RinaEngine):
    """A core that remembers whether it reached for its own microphone."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.reached_for_device = False


def make(ears_outside):
    settings = MemorySettings({
        "stt_engine": "vosk", "custom_commands": [], "reminders": [],
        "history": [], "listen_seconds": 3,   # the core takes no less anyway
    })
    engine = Watcher(settings=settings)
    engine.ears_outside = ears_outside
    said = []
    engine.voice_out = lambda text, **kw: said.append(text)

    # A watcher on the one place where the core takes the device. On the
    # **attempt**, not the result: the question is exactly whether the core
    # reaches for a microphone, not what comes of it.
    import voice.stt as stt

    original = stt.get_engine

    def watched(name):
        engine.reached_for_device = True
        return original(name)

    stt.get_engine = watched
    return engine, said, (lambda: setattr(stt, "get_engine", original))


print("=== оболочка на связи: ядро микрофон не трогает ===")
engine, said, undo = make(ears_outside=True)
try:
    events = []
    for name in ("listening.started", "listening.stopped"):
        engine.bus.on(name, (lambda n: lambda payload: events.append(n))(name))
    engine.listen_once()
    import time

    time.sleep(4.5)
    check("ядро не полезло за устройством", not engine.reached_for_device)
    check("но объявило, что слушает", "listening.started" in events,
          f"| {events}")
    check("и что перестало", "listening.stopped" in events, f"| {events}")
finally:
    undo()

print()
print("=== оболочки нет: ядро слушает само, как в 3.1.0 ===")
engine, said, undo = make(ears_outside=False)
try:
    engine.listen_once()
    import time

    time.sleep(1.5)
    check("ядро взяло устройство само", engine.reached_for_device)
finally:
    undo()

print()
print("ИТОГО ошибок:", fails)
sys.exit(1 if fails else 0)
