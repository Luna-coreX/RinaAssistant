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
    # An engine that does nothing: speaking tells it how long the reply
    # was (`4.0b-E06`, the conversation window), and a bare skeleton has
    # nobody to tell.
    made.engine = type("Nobody", (), {
        "talk_after_speaking": staticmethod(lambda seconds: None)})()
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
print("=== реплика режется на предложения ===")
# `4.0b-E09`. Where **not** to cut matters more than where to: a dot
# inside a number, a dot after an abbreviation, a dot before a lower-case
# letter. A seam in the middle of a sentence sounds worse than a wait.
from core.speech import LEAST_PIECE, sentences

cases = [
    ("Я могу запускать приложения и считать. Попробуй сказать: запусти браузер.",
     2, "обычные два предложения"),
    ("Скачано 10.5 МБ из 46.2 МБ, осталось совсем немного времени.",
     1, "точка внутри числа"),
    ("Открыла браузер, календарь и т.д. Больше ничего не запускала.",
     1, "точка после сокращения"),
    ("Готово. Ещё что-нибудь?", 1, "слишком короткое приклеивается к следующему"),
    ("Первое предложение достаточно длинное. Второе тоже вполне себе "
     "длинное. И третье не короче прочих.", 3, "три длинных остаются тремя"),
    ("Без знаков препинания просто длинная фраза", 1, "нечего резать"),
    ("", 0, "пусто"),
]
for text, want, why in cases:
    got = sentences(text)
    check(f"{why}", len(got) == want, f"| {len(got)} вместо {want}: {got}")

check("короткий кусок не остаётся один",
      all(len(part) >= LEAST_PIECE or len(got) == 1
          for text, _, _ in cases
          for got in [sentences(text)] for part in got),
      "| иначе очередь пустеет между половинами ответа")

print()
print("=== и первое предложение звучит, пока делается остальное ===")
# The gain itself. A reply of four sentences must not wait for the fourth
# to be synthesised before the first is heard: that is exactly the wait
# that made a long answer feel like a hang.


class Slow:
    """
    A synthesiser that takes its time, like a real one over the network.

    **By the length of the text, not by the call.** The first cut of this
    slept a fixed quarter-second per call, and then a whole reply cost
    exactly as much as its first sentence — so the timing check below
    stayed green with the splitting deliberately removed. A stand-in that
    does not scale the way the real thing scales measures nothing.
    """

    name = "медленное"
    sample_rate = 24000
    PER_CHARACTER = 0.006

    def __init__(self):
        self.said = []

    @staticmethod
    def available():
        return True

    def synthesize(self, text, voice="", rate=100):
        _time.sleep(len(text) * self.PER_CHARACTER)
        self.said.append(text)
        return speech.tone(1.0, rate=24000)


reply = ("Первое предложение достаточно длинное. Второе тоже вполне себе "
         "длинное. И третье не короче прочих. Четвёртое завершает ответ.")

slow, slow_pipe = speaker()
slow.synthesiser = Slow()
slow._settings = lambda: MemorySettings({"voice": "", "speed": 100})
slow._speech_wanted = ()
slow._speech_given = (True, True)
slow._said_mute = False

first = []
watch = Playing(slow, slow_pipe)


def note_first():
    while not first:
        piece = slow_pipe.recv()
        if piece:
            first.append(_time.perf_counter())
        else:
            _time.sleep(0.002)


threading.Thread(target=note_first, daemon=True).start()
began = _time.perf_counter()
slow._speak(reply)
whole = _time.perf_counter() - began
until(lambda: first, seconds=5.0)

check("реплика разошлась по предложениям", len(slow.synthesiser.said) == 4,
      f"| {slow.synthesiser.said}")
if first:
    waited = (first[0] - began) * 1000
    # Four sentences at a quarter of a second each: the whole reply takes
    # about a second to make, the first sentence a quarter of it. The
    # ceiling sits between the two — what is asked is "did the first go
    # out before the last was made", not "how fast is this computer".
    check("первый звук ушёл, не дожидаясь последнего предложения",
          waited < 600, f"| через {waited:.0f} мс при всей реплике "
                        f"за {whole * 1000:.0f} мс")

print()
print("=== предложение уходит, пока его ещё делают ===")
# `4.0b-E10`. Even one sentence is waited out whole today: the request
# goes and nothing is heard until its last byte comes back. Sent as it
# arrives, the first sound leaves for the shell while the rest is still
# being spoken on somebody else's computer.


class Trickling:
    """A synthesiser that hands over pieces, slowly, like a network one."""

    name = "по кускам"
    sample_rate = 24000
    streams = True
    PER_PIECE = 0.05

    def __init__(self, pieces=6, gives=True):
        self.pieces = pieces
        self.gives = gives
        self.asked = []

    @staticmethod
    def available():
        return True

    def stream(self, text, voice="", rate=100):
        self.asked.append(text)
        for _ in range(self.pieces if self.gives else 0):
            _time.sleep(self.PER_PIECE)
            yield speech.tone(0.1, rate=24000)

    def synthesize(self, text, voice="", rate=100):
        _time.sleep(self.PER_PIECE * self.pieces)
        return speech.tone(0.6, rate=24000)


def saying(voice_box):
    said = speaker()[0]
    said.synthesiser = voice_box
    said._settings = lambda: MemorySettings({"voice": "", "speed": 100})
    said._speech_wanted = ()
    said._speech_given = (True, True)
    said._said_mute = False
    return said


flowing = Trickling()
core = saying(flowing)
began = _time.perf_counter()
arrived = []
core.send_speech = lambda pcm, hertz: arrived.append(
    (_time.perf_counter() - began, len(pcm)))
core._speak("Одно предложение, довольно длинное, но всё же одно.")
whole = _time.perf_counter() - began

check("кусков ушло столько, сколько пришло", len(arrived) == 6,
      f"| {len(arrived)}")
if arrived:
    # Six pieces at fifty milliseconds: the sentence takes about three
    # tenths of a second to make, the first piece a twentieth of it.
    check("первый ушёл, не дожидаясь последнего",
          arrived[0][0] < whole / 2,
          f"| первый через {arrived[0][0] * 1000:.0f} мс при всей "
          f"фразе за {whole * 1000:.0f} мс")

# An engine that gave out nothing at all is tried the old way: it may
# simply have failed, and one more attempt costs a wait but saves a
# silence.
empty = Trickling(gives=False)
fell_back = saying(empty)
sent = []
fell_back.send_speech = lambda pcm, hertz: sent.append(len(pcm))
fell_back._speak("Ничего не пришло потоком.")
check("пустой поток — пробуем целиком", len(sent) == 1, f"| {sent}")

print()
print("=== декодирование идёт вместе с приходом ===")
# The other half. An engine that hands over sound as it makes it is of
# no use if the decoder waits for the last byte.
try:
    import av
except ImportError:
    print("     пропущено: PyAV в этом питоне нет "
          "(он стоит там же, где ядро — в venv)")
else:
    import threading as _threading

    def mp3_of(seconds):
        """A real mp3, made here, so the check needs no network."""
        raw = io.BytesIO()
        box = av.open(raw, mode="w", format="mp3")
        out = box.add_stream("mp3", rate=24000)
        out.layout = "mono"
        frame = av.AudioFrame.from_ndarray(
            numpy.frombuffer(speech.tone(seconds, rate=24000),
                             dtype="int16").reshape(1, -1),
            format="s16", layout="mono")
        frame.rate = 24000
        for packet in out.encode(frame):
            box.mux(packet)
        for packet in out.encode(None):
            box.mux(packet)
        box.close()
        return raw.getvalue()

    import numpy

    sound = mp3_of(3.0)

    def trickle(data, pieces=30, pause=0.01):
        step = max(1, len(data) // pieces)
        for at in range(0, len(data), step):
            _time.sleep(pause)
            yield data[at:at + step]

    began = _time.perf_counter()
    first = None
    samples = 0
    for pcm, hertz in speech.pcm_from_stream(trickle(sound)):
        if first is None:
            first = _time.perf_counter() - began
        samples += len(pcm) // 2
    whole = _time.perf_counter() - began

    check("поток разобрался", samples > 0, f"| {samples / 24000:.1f} с звука")
    # The mp3 arrives over about three tenths of a second. The first
    # frame must come out near the beginning of that, not at its end —
    # and it did come out at the end while the reader waited for a full
    # thirty-two-kilobyte mouthful before handing anything over.
    check("первый звук — в начале прихода, а не в конце",
          first is not None and first < whole / 2,
          f"| первый через {first * 1000:.0f} мс, всё за {whole * 1000:.0f} мс")

print()
print("=== перебить можно словом ===")
# `4.0b-E12`. The microphone stays open while she talks, because a
# person who cannot cut in stops talking to her and starts waiting her
# out — and waiting somebody out is not a conversation. Two things then
# have to hold: her own voice must not count as somebody speaking, and
# the words that cut in must actually cut.
import collections as _collections


class Ear:
    """A recogniser that gives back whatever it was told to."""

    name = "подсказанное"
    streams = False

    def __init__(self, text):
        self.text = text

    @staticmethod
    def available():
        return True

    def recognise(self, pcm, language="ru"):
        return speech.Heard(text=self.text)


def listening(heard_text, said_before=(), wake=("рина",), talking=True):
    """
    A core that has just heard `heard_text` and lately said the rest.

    `talking` is whether speech of hers is in flight — because that is
    what makes interrupting mean anything. Interrupting silence is not
    an interruption, and saying so in the journal would teach a person
    to stop reading the word.
    """
    box = ProtocolServer.__new__(ProtocolServer)
    box._talking_out = talking
    box.recogniser = Ear(heard_text)
    box.heard = {"bytes": 0, "frames": 0, "loud_frames": 0, "phrases": 0,
                 "recognitions": 0, "texts": 0, "dropped": 0}
    box._settings = lambda: MemorySettings({"wake_words": list(wake)})
    box._lately_said = _collections.deque(said_before, maxlen=4)
    box._speech_queue = None
    box.ids = Ids()
    box.sent = []
    box.send = lambda envelope: box.sent.append(envelope.method)
    box.routed = []
    box.announced = []

    class Engine:
        class bus:
            @staticmethod
            def emit(name, **fields):
                box.announced.append((name, fields.get("text", "")))

        @staticmethod
        def is_always_listen():
            return True

        @staticmethod
        def handle_command_async(text, source="voice", require_wake=False):
            box.routed.append(text)

    box.engine = Engine()
    return box


mine = listening("я могу запускать приложения и считать",
                 said_before=["Я могу запускать приложения и считать."])
mine._recognise(b"\x00\x00")
check("свои же слова обратно — не в счёт",
      mine.announced == [] and mine.routed == [],
      f"| {mine.announced}, {mine.routed}")
check("и речь из-за них не рвётся", "speech.stop" not in mine.sent,
      f"| {mine.sent}")

# Not a word-for-word match: recognition of one's own voice through a
# speaker is imperfect, and demanding an exact one would let every
# second echo through.
askew = listening("я могу запускать приложение и считать",
                  said_before=["Я могу запускать приложения и считать."])
askew._recognise(b"\x00\x00")
check("и расслышанные с ошибкой — тоже", askew.announced == [],
      f"| {askew.announced}")

stopped = listening("стоп", said_before=["Я могу запускать приложения."])
stopped._recognise(b"\x00\x00")
check("«стоп» обрывает речь", "speech.stop" in stopped.sent,
      f"| {stopped.sent}")
# "Stop" was about the talking, and the talking has stopped: carrying it
# on to the router afterwards would look for a command called "стоп".
check("и командой не становится", stopped.routed == [],
      f"| {stopped.routed}")
check("но человек видит, что его услышали",
      [n for n, _ in stopped.announced] == ["speech.recognized"],
      f"| {stopped.announced}")

named = listening("рина сколько времени",
                  said_before=["Я могу запускать приложения."])
named._recognise(b"\x00\x00")
check("имя тоже обрывает речь", "speech.stop" in named.sent, f"| {named.sent}")
check("и фраза при этом доходит до разбора",
      named.routed == ["рина сколько времени"], f"| {named.routed}")

quiet = listening("какая сегодня погода",
                  said_before=["Я могу запускать приложения."])
quiet._recognise(b"\x00\x00")
check("прочее речь не рвёт", "speech.stop" not in quiet.sent, f"| {quiet.sent}")

# And when she is not talking, there is nothing to interrupt. Without
# this every phrase with her name in it — that is, most of them in
# "always listening" — would announce an interruption of nothing.
silent = listening("рина сколько времени", talking=False)
silent._recognise(b"\x00\x00")
check("молчащую не перебивают", "speech.stop" not in silent.sent,
      f"| {silent.sent}")
check("а фраза всё равно разбирается",
      silent.routed == ["рина сколько времени"], f"| {silent.routed}")

print()
print("=== перебитое не договаривается ===")
# Stopping the sending leaves up to a second of sound already in the
# shell's queue; stopping the playing leaves the rest of the reply still
# to come. A person who interrupted hears the difference at once.
cut, cut_pipe = speaker()
cut.sent = []
cut.send = lambda envelope: cut.sent.append(envelope.method)
cut.synthesiser = Slow()
cut._settings = lambda: MemorySettings({"voice": "", "speed": 100})
cut._speech_wanted = ()
cut._speech_given = (True, True)
cut._said_mute = False
cut._lately_said = None

# Nothing is stubbed here: the sound really goes down the pipe, so
# "she is talking" is true because she is, and not because the check
# said so.
taken = Playing(cut, cut_pipe).start()


def interrupt_once_started():
    while not taken.taken:
        _time.sleep(0.005)
    cut.hush()


threading.Thread(target=interrupt_once_started, daemon=True).start()
cut._speak("Первое предложение достаточно длинное. Второе тоже вполне себе "
           "длинное. И третье не короче прочих. Четвёртое завершает ответ.")
until(lambda: cut._cut_in, seconds=5.0)
_time.sleep(0.3)
taken.stop = True
said = cut.synthesiser.said
check("остаток реплики не сказан", len(said) < 4,
      f"| произнесено предложений {len(said)} из четырёх")
check("и оболочке велено замолчать", "speech.stop" in cut.sent,
      f"| {cut.sent}")

print()
print("=== ядро сообщает, сколько говорило ===")
# The arithmetic above is only worth anything if somebody supplies the
# number. Four sentences, a second of sound each.
counted, counted_pipe = speaker()
counted.synthesiser = Slow()
counted._settings = lambda: MemorySettings({"voice": "", "speed": 100})
counted._speech_wanted = ()
counted._speech_given = (True, True)
counted._said_mute = False
counted._lately_said = None
counted.send_speech = lambda pcm, hertz: None

held = []


class Held:
    @staticmethod
    def talk_after_speaking(seconds):
        held.append(seconds)


counted.engine = Held()
counted._speak("Первое предложение достаточно длинное. Второе тоже вполне "
               "себе длинное. И третье не короче прочих. Четвёртое "
               "завершает ответ.")
check("длительность реплики посчитана и передана",
      len(held) == 1 and 3.5 < held[0] < 4.5,
      f"| {held} с при четырёх секундах звука")

print()
print("ИТОГО ошибок:", fails)
sys.exit(1 if fails else 0)
