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
import io
import math
import os
import struct
import sys

sys.path.insert(0, r"C:\DevStation\PCDev\DesktopApps\RinaAssistant")

# The model is read from the real profile, and nothing else is: its folder
# is kept before the profile is moved, and everything the check writes —
# the call journal among it — goes into a folder of its own. Measured, it
# wrote `audit.db` into the developer's profile.
REAL_APPDATA = os.environ.get("APPDATA", "")
from sandbox import isolate_storage
isolate_storage()

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
print("=== распознавание слушает по ходу фразы ===")
# `4.0b-E07`. An engine that can listen as it goes must be given the
# phrase **as it is being said**, not after — otherwise its whole cost
# lands after the person has stopped talking. Measured on the real
# model: 596 ms that way, 14 ms this way, the same words.
#
# Checked without a model first, because this part is plumbing and has
# to hold for every engine: what is fed, in what order, and what happens
# to a phrase that came to nothing.


class Aloud:
    """A stand-in that listens as it goes and writes down what it was given."""

    name = "вслух"
    streams = True

    def __init__(self):
        self.parts = []
        self.finished = 0
        self.forgotten = 0

    @staticmethod
    def available():
        return True

    def feed(self, pcm):
        self.parts.append(pcm)

    def finish(self):
        self.finished += 1
        return Heard(text="услышано")

    def reset(self):
        self.forgotten += 1
        self.parts = []

    def recognise(self, pcm, language="ru"):       # must never be called
        self.parts.append(b"WHOLE")
        return Heard(text="целиком")


ear = Aloud()
live = ProtocolServer.__new__(ProtocolServer)
live.engine = Recorder()
live.segmenter = Segmenter()
live.recogniser = ear
live.heard = {"bytes": 0, "frames": 0, "loud_frames": 0, "phrases": 0,
              "recognitions": 0, "texts": 0, "dropped": 0}
live._phrases = None
live._stt_thread = None

step = int(RATE * 0.1) * 2
spoken = silence(0.5) + sound(0.2, 0.01) + sound(0.8, 0.3) + silence(1.2)
for at in range(0, len(spoken), step):
    live._hear(spoken[at:at + step])
for _ in range(100):
    if ear.finished:
        break
    time.sleep(0.02)

check("фраза дошла по частям, а не целиком",
      ear.parts and b"WHOLE" not in ear.parts,
      f"| частей {len(ear.parts)}")
check("и в конце спросили слова один раз", ear.finished == 1,
      f"| {ear.finished}")
# What is fed is not the chunks that arrived — those include the silence
# before the phrase — but exactly what the segmenter took, run-up and
# all. Anything else and the first word loses its beginning again, one
# floor below where that was just fixed.
fed = b"".join(ear.parts)
windows = [fed[at:at + step] for at in range(0, len(fed), step)]
louds = [i for i, w in enumerate(windows) if Segmenter.level(w) >= 0.02]
run_up = windows[max(0, louds[0] - 2):louds[0]] if louds else []
quiet = Segmenter.level(b"".join(run_up)) if run_up else 0.0
check("и перед громким местом в них тихое начало слова",
      len(run_up) == 2 and 0.0 < quiet < 0.02,
      f"| {len(run_up)} кадров, громкость {quiet:.4f}")

# A phrase too short to be one: the engine has been fed it and has to be
# told to forget, or its words turn up glued to the front of the next.
short = Aloud()
tiny = ProtocolServer.__new__(ProtocolServer)
tiny.engine = Recorder()
tiny.segmenter = Segmenter()
tiny.recogniser = short
tiny.heard = {"bytes": 0, "frames": 0, "loud_frames": 0, "phrases": 0,
              "recognitions": 0, "texts": 0, "dropped": 0}
tiny._phrases = None
tiny._stt_thread = None
brief = sound(0.1, 0.3) + silence(1.2)
for at in range(0, len(brief), step):
    tiny._hear(brief[at:at + step])
for _ in range(100):
    if short.forgotten:
        break
    time.sleep(0.02)
check("слишком короткое — велено забыть, а не досказать",
      short.forgotten == 1 and short.finished == 0,
      f"| забыто {short.forgotten}, спрошено {short.finished}")

print()
print("=== и на настоящей модели это стоит миллисекунды ===")
# The gain itself, on the real model and at the speed a person speaks.
# Fed in a tight loop the difference disappears — all the work simply
# happens at the end either way — so the sound arrives here in real
# time, a tenth of a second at a time, as it does from the shell.
from core.speech import VoskRecogniser

vosk_model = os.path.join(
    REAL_APPDATA, "RinaAssistant", "models",
    "vosk-ru-small", "vosk-model-small-ru-0.22")
here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
recording = os.path.join(here, "tools", "fixtures", "said-rina.wav")

real = VoskRecogniser(vosk_model)
if not os.path.isfile(recording):
    print("     пропущено: нет записи")
elif not real.available():
    # The package lives where the core lives, and the regression may be
    # run by another interpreter. Naming what is missing is the
    # difference between a skip and a mystery.
    print(f"     пропущено: {real._error or 'Vosk недоступен в этом питоне'}")
else:
    said = []

    class Listener:
        """The engine, reduced to the one event this measurement needs."""

        class bus:
            @staticmethod
            def emit(name, **fields):
                if name == "speech.recognized":
                    said.append((time.perf_counter(), fields["text"]))

        @staticmethod
        def is_always_listen():
            return False

        @staticmethod
        def handle_command_async(*args, **rest):
            pass

    real._load()
    fast = ProtocolServer.__new__(ProtocolServer)
    fast.engine = Listener()
    fast.segmenter = Segmenter()
    fast.recogniser = real
    fast.heard = {"bytes": 0, "frames": 0, "loud_frames": 0, "phrases": 0,
                  "recognitions": 0, "texts": 0, "dropped": 0}
    fast._phrases = None
    fast._stt_thread = None

    with open(recording, "rb") as file:
        voice = file.read()[44:]
    coming = voice + silence(2.0)
    cut = None
    for at in range(0, len(coming), step):
        began = time.perf_counter()
        before = fast.heard["phrases"]
        fast._hear(coming[at:at + step])
        if fast.heard["phrases"] > before:
            cut = time.perf_counter()
        time.sleep(max(0.0, 0.1 - (time.perf_counter() - began)))
    for _ in range(300):
        if said:
            break
        time.sleep(0.01)

    check("фраза распозналась", said, f"| {[text for _, text in said]}")
    check("и распознана верно",
          said and "рина" in said[0][1].lower(),
          f"| {said[0][1] if said else ''}")
    if said and cut:
        tail = (said[0][0] - cut) * 1000
        # Handing the phrase over whole costs 596 ms here; listening as
        # it goes costs 14. The ceiling is set between the two and much
        # nearer the slow one, so that a busy machine does not redden it:
        # what is asked is "was the work done in advance", not "how fast
        # is this computer".
        check("и слова готовы почти сразу после нарезки", tail < 250,
              f"| {tail:.0f} мс после конца фразы")

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
print("=== имена программ: распознаванию подсказано, что установлено ===")
# `4.0b-V08`. Ordinary Russian came through and the names of programs did
# not: «запусти Стим» three times in twenty, the rest «запустите им»,
# «с тем», «запустисти». Hinted with how the installed programs are said,
# the recognition bench launched 24 commands of 28 instead of 13. These
# are the joints of that: the table the hints come from, the choice of
# what goes in, and — on the real model, where there is one — a phrase
# that is misheard without them.
from core import apps as apps_mod
from voice import app_launcher

# Every hint leads back to its program. A hint the matcher cannot use is a
# word the model was taught for nothing: «Блокнот» was one, on a Windows
# where the program is called Notepad.
named = [apps_mod.AppEntry(target.title(), target, "file", "start_menu")
         for target in apps_mod.SAID_AS]
lost = [said for target, said in apps_mod.SAID_AS.items()
        if target.title() not in [e.name for e in
                                  apps_mod.find(said, limit=5, entries=named)]]
check("каждая подсказка ведёт к своей программе", not lost,
      f"| не ведут: {lost}")

# And none of them is a mishearing. The table of spoken names carries
# «стимул» for Steam because that is what the matcher is handed; offered
# as a hint, it would teach the model to write the mistake.
misheard = {"стимул", "фотошок", "телеграмм"}
check("среди подсказок нет ослышек",
      not misheard & {apps_mod.normalize(s) for s in apps_mod.SAID_AS.values()})

steam = apps_mod.AppEntry("Steam", "steam.lnk", "file", "start_menu")
# A helper in PATH that shares a word with a program is not the program:
# counted, it would put «Хром» into the hints of a machine without Chrome.
tool = apps_mod.AppEntry("chrome-helper", "helper.exe", "file", "path")
given = apps_mod.spoken_hints([steam, tool], ("Рина", "код"))
check("подсказано установленное, первым — имя и слова человека",
      given[:3] == ["Рина", "код", "Стим"] and "Хром" not in given,
      f"| {given}")
check("и не больше предела",
      len(apps_mod.spoken_hints(named, ("Рина",))) <= apps_mod.HINTS_AT_MOST)

# The name she answers to, not the wake words: those carry the mishearings
# a person added so that a misheard name still wakes her, and a hint is
# what the model is pulled towards.
engine_h = RinaEngine(settings=MemorySettings({
    "stt_engine": "disabled", "custom_commands": [], "reminders": [],
    "history": [], "wake_words": ["Rina", "Рина", "Рена", "Рима"],
    "app_aliases": {"код": "Visual Studio Code"},
}))
engine_h.apps_source = lambda: [steam.to_dict()]
hinting = ProtocolServer.__new__(ProtocolServer)
hinting.engine = engine_h
hinting._hints, hinting._hints_for = "", None
line = hinting._recognition_hints()
check("ядро подсказывает имя, а не ослышки из слов активации",
      line.startswith("Рина") and "Рена" not in line and "Рима" not in line
      and "Стим" in line and "код" in line, f"| «{line}»")

# «запусти стим» and «запустите им» are one sound, and recognition settles
# on the longer verb. The name then comes through behind a polite verb,
# and a verb the launcher does not know launches nothing.
decided = app_launcher.decide("Рина, запустите Стим", apps=[steam])
check("вежливая форма тоже запускает",
      decided is not None and decided.entry is steam,
      f"| {getattr(decided, 'status', None)}")

if not whisper_at_hand():
    print("     пропущено: модели whisper на этой машине нет")
else:
    # Said by Rina's own voice, so the recording can live here: the bench
    # used four voices, and this is the one that belongs to the project.
    # Without hints the model hears «Запусти вяжёл студия Кот». Chosen
    # because it comes right under any list that holds the program — the
    # program alone, five, or the twenty-one of the bench's machine. A
    # phrase that came right under one list and not another would be a
    # check on the list, and «Рина, запусти Стим» was exactly that.
    import wave as wave_mod

    from core import speech as speech_mod

    here_fixtures = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "fixtures")
    with wave_mod.open(os.path.join(here_fixtures, "said-launch-code.wav"),
                       "rb") as f:
        launch = f.readframes(f.getnframes())
    with wave_mod.open(os.path.join(here_fixtures, "said-rina.wav"), "rb") as f:
        asked = f.readframes(f.getnframes())
    code = apps_mod.AppEntry("Visual Studio Code", "code.lnk", "file",
                             "start_menu")
    hinted_ear = speech_mod.whisper_for(
        MemorySettings({"whisper_model": "base"}),
        hints=lambda: ", ".join(apps_mod.spoken_hints([code], ("Рина",))))
    heard_code = hinted_ear.recognise(launch)
    check("с подсказкой имя программы слышно", "вижуал студио код" in
          apps_mod.normalize(heard_code.text), f"| {heard_code.text!r}")
    ran = app_launcher.decide(heard_code.text, apps=[code])
    check("и фраза запускает её",
          ran is not None and ran.entry is code, f"| {heard_code.text!r}")

    # And a hint the list could not give — a broken shell, a settings store
    # that threw — costs the hint, not the phrase.
    def broken():
        raise RuntimeError("оболочка не ответила")
    shaky = speech_mod.whisper_for(
        MemorySettings({"whisper_model": "base"}), hints=broken)
    kept_on = shaky.recognise(asked)
    check("сломанные подсказки не отнимают распознавание",
          kept_on.ok and "умеешь" in kept_on.text.lower(),
          f"| {kept_on.text!r}")

print()
print("=== фразы сохраняются только по просьбе ===")
# `RINA_KEEP_PHRASES` keeps every phrase as recognition got it — a
# recording of somebody's voice, for a diagnosis (`4.0b-V08`). Nothing may
# be written without it: not by a setting, not by a default.
import json
import tempfile

from core.speech import Heard


class HeardIt:
    """A recogniser that hears one sentence, whatever it is given."""

    @staticmethod
    def available():
        return True

    @staticmethod
    def recognise(pcm):
        return Heard(text="что ты умеешь")


keeper = ProtocolServer.__new__(ProtocolServer)
keeper.engine = engine
keeper.recogniser = HeardIt()
keeper._hints = "Рина"
keeper.heard = {"recognitions": 0, "texts": 0}
kept_in = os.path.join(tempfile.mkdtemp(), "phrases")
os.environ.pop(ProtocolServer.KEEP_PHRASES, None)
keeper._recognise(sound(1.0))
check("без переменной не сохраняется ничего", not os.path.exists(kept_in))
os.environ[ProtocolServer.KEEP_PHRASES] = kept_in
try:
    keeper._recognise(sound(1.0))
finally:
    os.environ.pop(ProtocolServer.KEEP_PHRASES, None)
listed = sorted(os.listdir(kept_in)) if os.path.isdir(kept_in) else []
records = ([json.loads(line) for line in
            io.open(os.path.join(kept_in, "phrases.jsonl"), encoding="utf-8")]
           if "phrases.jsonl" in listed else [])
check("с ней — звук и запись о нём",
      len(records) == 1 and records[0]["file"] in listed
      and records[0]["text"] == "что ты умеешь",
      f"| {listed}")

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
