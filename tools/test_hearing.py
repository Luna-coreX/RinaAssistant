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
print("=== начало первого слова не съедается ===")
# **The one that mattered.** A word opens quieter than it goes on, and the
# chunk holding that opening is below the threshold. Thrown away, it took
# the beginning of the first word with it — and in "always listening" the
# first word is the name. The real recording went in as «Рина, что ты
# умеешь?» and came out of Vosk as «приятно что ты умеешь»: not a mishearing
# but a phrase handed over without its start.
#
# Fed in the hundred-millisecond chunks the shell actually sends, because
# the loss is exactly one chunk and a whole-buffer feed cannot show it.
onset = Segmenter()
attack, body = 0.2, 0.8
speech = sound(attack, 0.01) + sound(body, 0.3)      # quiet start, then voice
for at in range(0, len(silence(0.5)), int(RATE * 0.1) * 2):
    onset.feed(silence(0.5)[at:at + int(RATE * 0.1) * 2])
for at in range(0, len(speech), int(RATE * 0.1) * 2):
    onset.feed(speech[at:at + int(RATE * 0.1) * 2])
caught = []
for at in range(0, len(silence(1.0)), int(RATE * 0.1) * 2):
    caught += onset.feed(silence(1.0)[at:at + int(RATE * 0.1) * 2])
check("фраза нарезалась", len(caught) == 1, f"| {len(caught)}")
if caught:
    # Measured where it matters: find the first loud moment inside the
    # phrase and look at what lies immediately before it. That has to be
    # the attack — audible, under the threshold — over its whole length.
    # Asking about the phrase's own first samples would only find the
    # run-up's silence, and asking about length would pass on a phrase
    # padded at the wrong end.
    step = int(RATE * 0.1) * 2
    windows = [caught[0][at:at + step] for at in range(0, len(caught[0]), step)]
    louds = [i for i, w in enumerate(windows) if Segmenter.level(w) >= 0.02]
    before = windows[max(0, louds[0] - int(attack / 0.1)):louds[0]] if louds else []
    head = Segmenter.level(b"".join(before)) if before else 0.0
    check("перед громким местом сохранилось тихое начало слова",
          len(before) == int(attack / 0.1) and 0.0 < head < 0.02,
          f"| {len(before)} кадров, громкость {head:.4f}")

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
print("=== микрофон закрыли посреди фразы ===")
# **The phrase that waited for the next one.** A phrase is cut out by the
# silence after it, and if the microphone shuts at that very moment no
# silence ever comes: the words stay in the buffer. They surfaced during
# the following listen, so Rina answered the previous phrase almost before
# the person had begun the new one — "she answers instantly and does not
# let me finish the command". Ending the stream ends the phrase.
from core.wire.envelope import Envelope

cut_off = ProtocolServer.__new__(ProtocolServer)
cut_off.engine = engine
cut_off.segmenter = Segmenter()
cut_off.recogniser = NoModel()
cut_off.heard = {"bytes": 0, "frames": 0, "loud_frames": 0, "phrases": 0,
                 "recognitions": 0, "texts": 0}
cut_off.incoming = {11: {"kind": "audio.input", "format": {},
                         "bytes": 0, "frames": 0}}
cut_off._hear(sound(0.8))                       # speech and no silence after
check("пока поток открыт, фраза ещё ждёт тишины",
      cut_off.hearing()["phrases"] == 0, f"| {cut_off.hearing()['phrases']}")
cut_off._stream_close(Envelope.request("stream.close", {"stream_id": 11},
                                       id="x"))
check("поток закрылся — фраза договорена",
      cut_off.hearing()["phrases"] == 1, f"| {cut_off.hearing()['phrases']}")

print()
print("=== распознавание идёт по одному и по порядку ===")
# Found in a person's journal, not by a check. Two phrases were heard and
# one line of recognised text came out — with the words of both inside it
# — ten seconds after the second one ended. Then "Failed to create a
# model", once per phrase, for the rest of the session.
#
# The cause was a thread per phrase over one shared recogniser holding one
# model loaded on first use. Two phrases close together loaded it twice at
# once and read it at once. What it looked like from the chair was worse
# than an error: Rina answered a second after you started speaking, and
# answered the thing you had said before.
#
# Two things are asked here, and the second is the one that survives a
# thread-safe engine: recognition happens **one at a time**, and results
# reach the engine **in the order the phrases were spoken**. A short
# phrase overtaking a long one is not a rare race — it is what always
# happens when both run at once.
import threading
import time

from core.speech import Heard


class SlowEar:
    """Recognises slowly and remembers whether it was ever asked twice."""

    def __init__(self):
        self.inside = 0
        self.together = 0
        self.order = []
        self._guard = threading.Lock()

    @staticmethod
    def available():
        return True

    def recognise(self, pcm, language="ru"):
        with self._guard:
            self.inside += 1
            self.together = max(self.together, self.inside)
        # The longer phrase takes longer, so that "in order" and "in the
        # order they happened to finish" give different answers.
        # By the sound handed over, and the boundary is between the two:
        # a phrase carries its trailing silence with it, so 0.4 s of voice
        # arrives as 1.4 s of bytes, and a threshold set by the spoken
        # length called both of them long.
        long_one = len(pcm) > 60000
        time.sleep(0.25 if long_one else 0.05)
        with self._guard:
            self.inside -= 1
            self.order.append(len(pcm))
        # Named after the sound it was handed, not after a counter. The
        # first edition numbered them as they finished, so "in order" was
        # true of any order at all — the check restated its own stand-in
        # and agreed with itself.
        return Heard(text="длинная" if long_one else "короткая")


class Recorder:
    """The engine, reduced to what this check asks of it."""

    def __init__(self):
        self.taken = []
        self.bus = type("Bus", (), {"emit": lambda *a, **k: None})()

    def is_always_listen(self):
        return False

    def handle_command_async(self, text, source="voice", require_wake=False):
        self.taken.append(text)


ear = SlowEar()
taker = Recorder()
listener = ProtocolServer.__new__(ProtocolServer)
listener.engine = taker
listener.segmenter = Segmenter()
listener.recogniser = ear
listener.heard = {"bytes": 0, "frames": 0, "loud_frames": 0, "phrases": 0,
                  "recognitions": 0, "texts": 0, "dropped": 0}
listener._phrases = None
listener._stt_thread = None

# A long phrase, then a short one, with just enough silence between them to
# be two phrases and not enough for the first to be finished with.
listener._hear(sound(1.6))
listener._hear(silence(1.0))
listener._hear(sound(0.4))
listener._hear(silence(1.0))
check("обе фразы нарезаны", listener.hearing()["phrases"] == 2,
      f"| {listener.hearing()['phrases']}")

for _ in range(100):
    if len(taker.taken) == 2:
        break
    time.sleep(0.05)

check("распознаны обе", len(taker.taken) == 2, f"| {taker.taken}")
check("одновременно — никогда", ear.together <= 1,
      f"| разом доходило до {ear.together}")
check("сказанное первым дошло до ядра первым",
      taker.taken[:2] == ["длинная", "короткая"],
      f"| {taker.taken}")
check("и распознавались они в том же порядке",
      len(ear.order) == 2 and ear.order[0] > ear.order[1],
      f"| {ear.order} байт")

print()
print("=== что не поспели распознать — сказано вслух ===")
# Dropping is lawful: recognition slower than speech has to lose
# something. Falling a minute behind is not, and neither is losing it
# quietly — a phrase that vanishes without a word is indistinguishable
# from a microphone that stopped working.


class Stuck:
    """Never finishes the first phrase, so the queue fills up."""

    def __init__(self):
        self.go = threading.Event()

    @staticmethod
    def available():
        return True

    def recognise(self, pcm, language="ru"):
        self.go.wait(5.0)
        return Heard(text="наконец")


jam = Stuck()
piled = ProtocolServer.__new__(ProtocolServer)
piled.engine = Recorder()
piled.segmenter = Segmenter()
piled.recogniser = jam
piled.heard = {"bytes": 0, "frames": 0, "loud_frames": 0, "phrases": 0,
               "recognitions": 0, "texts": 0, "dropped": 0}
piled._phrases = None
piled._stt_thread = None

for _ in range(ProtocolServer.PHRASE_QUEUE + 3):
    piled._hear(sound(0.4))
    piled._hear(silence(1.0))

check("очередь не растёт без предела",
      piled.hearing()["dropped"] > 0,
      f"| отброшено {piled.hearing()['dropped']} из "
      f"{piled.hearing()['phrases']}")
check("и лишнее именно отброшено, а не потеряно молча",
      piled.hearing()["dropped"]
      == piled.hearing()["phrases"] - ProtocolServer.PHRASE_QUEUE - 1,
      f"| фраз {piled.hearing()['phrases']}, очередь "
      f"{ProtocolServer.PHRASE_QUEUE}, одна в работе, "
      f"отброшено {piled.hearing()['dropped']}")
jam.go.set()

print()
print("=== тишину распознаватель молчанием и считает ===")
# **Whisper answers something to anything.** In a person's journal a
# phrase of 1.2 seconds from a quiet room came back as "Редактор
# субтитров Н.Семкирова" — a line of subtitle credits out of the data it
# was trained on — and the assistant went and searched the internet for
# it. Reproduced here before it was fixed: on a second of digital silence
# this model gives that very phrase, with a `no_speech_prob` of 0.71.
#
# Asked of the real model, because there is nothing else to ask: the
# hallucination is a property of the model, and a stand-in would only
# repeat what the check's author already believes. On a machine where the
# model is not downloaded the question is skipped, out loud — it is never
# fetched from here, since a check that starts a hundred-megabyte
# download is a check nobody runs twice.


def whisper_at_hand(size="base"):
    """The model if it is already on this machine, else None."""
    try:
        from faster_whisper import WhisperModel
        WhisperModel(size, device="cpu", compute_type="int8",
                     local_files_only=True)
        return True
    except Exception:
        return False


from core.settings_api import MemorySettings

if not whisper_at_hand():
    print("     пропущено: модели whisper на этой машине нет")
else:
    from core import speech as speech_mod

    ear = speech_mod.whisper_for(
        MemorySettings({"whisper_model": "base"}))
    check("движок — тот, что едет в сборке",
          type(ear).__name__ == "FasterWhisperRecogniser",
          f"| {type(ear).__name__}")

    # Two things stop it — the voice filter and the model's own opinion of
    # whether that was speech — and this asks neither of them: it asks
    # what came out. Taking the filter away leaves this green, and rightly
    # so: the other gate still holds the outcome, and nothing a person
    # would notice has changed. What is checked is silence in, silence
    # out.
    quiet = ear.recognise(silence(1.2))
    check("на тишине не сочиняется ничего",
          quiet.ok and not quiet.text, f"| {quiet.text!r}")

    # And the other side, or the check would be green on a recogniser
    # that had gone deaf: a gate that lets nothing through passes the
    # question above perfectly.
    fixture = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "fixtures", "said-rina.wav")
    import wave as wave_mod

    with wave_mod.open(fixture, "rb") as f:
        said = f.readframes(f.getnframes())
    heard_it = ear.recognise(said)
    check("а речь проходит", "умеешь" in heard_it.text.lower(),
          f"| {heard_it.text!r}")

    # As the segmenter really hands it over: a phrase carries the silence
    # that ended it, and most of what reaches the model is that silence.
    # The first cut at this dropped the phrase along with the pause.
    with_tail = ear.recognise(said + silence(1.0))
    check("и проходит вместе с хвостом тишины",
          "умеешь" in with_tail.text.lower(), f"| {with_tail.text!r}")

print()
print("=== предлагается только то, что можно построить ===")
# A person chose `whisper` in the settings and heard "recognition is
# unavailable": the list of choices came from the 3.1.0 engines, which open
# their own microphone, while the streaming path knew one name and quietly
# answered "disabled" to every other. Two lists, one offering what the other
# cannot do — and the person meets the gap as silence.
from core.settings_schema import options_for
from core.speech import RECOGNISERS

offered = {o["value"]
           for o in options_for("stt_engine", MemorySettings({}))}
buildable = set(RECOGNISERS)
check("каждый предлагаемый движок ядро умеет построить",
      offered <= buildable, f"| лишние: {sorted(offered - buildable)}")
check("и ни один умеемый не спрятан",
      buildable <= offered, f"| спрятаны: {sorted(buildable - offered)}")

# Availability is a separate question from being offered, and it is right
# that it is: a person is entitled to see that an engine exists and is not
# installed. What must never happen is an engine that can be chosen and
# cannot be built.
for name in sorted(buildable):
    built = RECOGNISERS[name](MemorySettings({}))
    check(f"«{name}» строится и отвечает про свою доступность",
          hasattr(built, "available") and isinstance(built.available(), bool))

# And asking must be cheap. This list is drawn every time a person opens the
# settings, and the first edition answered by importing: `import whisper`
# pulls in torch, so naming three engines took two and a half seconds. The
# edition before that loaded the model to answer, which on a fresh machine
# would have started a download from a settings page.
import time

started = time.time()
options_for("stt_engine", MemorySettings({}))
spent = time.time() - started
check("список движков рисуется мгновенно", spent < 0.5,
      f"| {spent:.2f} с")

# "Off" is the choice of having no recognition, and it can never be
# unavailable. Asking a recogniser gets "no" — which is what it means, and
# which greyed out the one option that cannot fail.
choices = {o["value"]: o for o in options_for("stt_engine", MemorySettings({}))}
check("«выключено» всегда можно выбрать",
      choices.get("disabled", {}).get("available") is True)

print()
print("ИТОГО ошибок:", fails)

# `os._exit`, because recognition runs in daemon threads and one of them is
# still alive when the interpreter starts to shut down — it dies holding the
# lock on stderr and turns a green check into a fatal error. The same reason
# `test_settings_api.py` leaves this way.
sys.stdout.flush()
sys.stderr.flush()
os._exit(1 if fails else 0)
