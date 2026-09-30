# -*- coding: utf-8 -*-
"""
Who answers, and what follows from it (`4.0b-E14`).

A personality is more than the model's instruction — `test_persona.py`
checks that part. Choosing one changes what she answers to and, when the
person gave it a voice, how she sounds. Both go through one door each —
`voice.wake.get_wake_words` and `core.speech.synthesiser_for` — and both are
checked here, along with the thing that makes a choice take effect at all:
the server rebuilding the voice when the personality changes, rather than
at the next start.

The rules, each a decision rather than a default:

**Called by its own words, or by its name.** A personality of the person's
own answers to the wake words given to it; with none, to its name. With
neither, Rina's words stay: an assistant nobody can call is worse than one
still called by the old name.

**Its voice only with the voice on.** «Без озвучки» is a choice about
speaking at all, and a personality's voice does not overrule it.

**Rina ignores what belongs to the other one.** The own personality's
words and voice file are kept when Rina is chosen, and change nothing.

To run:
    python tools/test_personality.py
"""
import os
import sys

sys.path.insert(0, r"C:\DevStation\PCDev\DesktopApps\RinaAssistant")
sys.path.insert(0, os.path.join(
    r"C:\DevStation\PCDev\DesktopApps\RinaAssistant", "tools"))

from sandbox import isolate_storage

isolate_storage()

from console import use_utf8
from core import speech
from core.settings_api import MemorySettings
from core.wire import server as wire_server
from core.wire.server import ProtocolServer
from voice.wake import get_wake_words

use_utf8()

fails = 0


def check(label, cond, detail=""):
    global fails
    if not cond:
        fails += 1
    print(("OK   " if cond else "FAIL "), label, detail)


RINA_WORDS = ["Рина", "Rina"]
VOICE = r"C:\voices\max.onnx"

print("=== слова активации ===")
check("Рину зовут её словами",
      get_wake_words({"wake_words": RINA_WORDS}) == ["рина", "rina"])
check("свою личность — её словами",
      get_wake_words({"personality": "own", "wake_words": RINA_WORDS,
                      "own_name": "Макс", "own_wake_words": ["Макс", "Max"]})
      == ["макс", "max"])
check("без слов — по имени",
      get_wake_words({"personality": "own", "wake_words": RINA_WORDS,
                      "own_name": "Макс"}) == ["макс"])
check("ни слов, ни имени — остаются слова Рины",
      get_wake_words({"personality": "own", "wake_words": RINA_WORDS})
      == ["рина", "rina"])
check("у Рины слова своей личности ничего не меняют",
      get_wake_words({"personality": "rina", "wake_words": RINA_WORDS,
                      "own_wake_words": ["Макс"], "own_name": "Макс"})
      == ["рина", "rina"])


def voice_of(**settings):
    return speech.synthesiser_for(settings)


print()
print("=== голос ===")
mine = voice_of(personality="own", own_voice_model=VOICE, tts_engine="edge")
check("своя личность говорит своим голосом",
      isinstance(mine, speech.PiperSynthesiser) and mine.model_path == VOICE,
      f"| {type(mine).__name__} {getattr(mine, 'model_path', '')!r}")
check("«без озвучки» сильнее голоса личности",
      isinstance(voice_of(personality="own", own_voice_model=VOICE,
                          tts_engine="silent"), speech.SilentSynthesiser))
plain = voice_of(personality="own", tts_engine="edge")
check("без своего голоса — голос из общих настроек",
      not isinstance(plain, speech.PiperSynthesiser), f"| {type(plain).__name__}")
rina = voice_of(personality="rina", own_voice_model=VOICE, tts_engine="edge")
check("у Рины голос своей личности не звучит",
      getattr(rina, "model_path", "") != VOICE, f"| {type(rina).__name__}")

print()
print("=== выбор действует сразу ===")
# The server as the running core has it, with only the voice's refresh in
# play: recognition is marked as given, so nothing heavier than choosing a
# synthesiser happens. What is checked is that switching the personality
# makes the voice stale — a choice that waits for a restart is a promise.


class Engine:
    pass


engine = Engine()
engine._settings = MemorySettings({"tts_engine": "edge", "personality": "rina",
                                   "own_voice_model": VOICE})
live = ProtocolServer.__new__(ProtocolServer)
live.engine = engine
live._speech_given = (True, False)
live.synthesiser = speech.synthesiser_for(engine._settings)
live._speech_wanted = tuple(str(engine._settings.get(key, "") or "")
                            for key in wire_server._VOICE_KEYS)
check("до выбора звучит голос из настроек",
      getattr(live.synthesiser, "model_path", "") != VOICE)
engine._settings.set("personality", "own")
live._voice_follows_settings()
check("выбрали свою личность — голос сменился без перезапуска",
      getattr(live.synthesiser, "model_path", "") == VOICE,
      f"| {type(live.synthesiser).__name__}")
engine._settings.set("own_voice_model", r"C:\voices\other.onnx")
live._voice_follows_settings()
check("и сменили ей голос — тоже",
      getattr(live.synthesiser, "model_path", "") == r"C:\voices\other.onnx",
      f"| {getattr(live.synthesiser, 'model_path', '')!r}")

print()
print("ИТОГО ошибок:", fails)
sys.exit(1 if fails else 0)
