# -*- coding: utf-8 -*-
"""
The recognition bench (`4.0b-V08`): what recognition hears, and what it
launches.

Measures, it does not check. The numbers depend on the machine — its
voices, its processor, the programs installed on it — and a check that
turned red when a voice was uninstalled would be measuring the machine.
`tools/test_hearing.py` holds the joints; this says how well they add up.

**The corpus.** Twenty commands said by the Windows voices (SAPI Irina,
OneCore Irina and Pavel) and by Rina's own Piper voice; Common Voice
sentences from the voice track's cache, real people on real microphones;
and a room with nobody speaking, to catch a model that invents. Every
clip is shaped the way the segmenter hands a phrase over: 16 kHz, 0.4 s
of run-up, 0.7 s of release, a quiet room instead of digital zeros.

**The measures.** Commands heard exactly; the program's name heard;
character error rate on ordinary sentences; **whether the phrase would
launch the right program** — through `app_launcher.decide` against this
machine's index, for the programs installed here, which is the one that
matters; text invented on noise; seconds per phrase with the model warm.

To run:
    python tools/hearing_bench.py build        make the corpus
    python tools/hearing_bench.py run [name]   measure; all when no name
"""
import csv
import io
import json
import os
import re
import statistics
import subprocess
import sys
import tempfile
import time
import wave

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

from console import use_utf8  # noqa: E402

use_utf8()

CACHE = os.path.expanduser("~/.cache/rina-voice")
HERE = os.path.join(CACHE, "hearing-bench")
CORPUS = os.path.join(HERE, "corpus")
RATE = 16000
LEAD, TAIL = 0.4, 0.7

PHRASES = [
    "Рина, запусти Стим", "Запусти Стим", "Открой Телеграм",
    "Запусти Дискорд", "Открой Гугл Хром", "Включи Спотифай",
    "Открой Обсидиан", "Запусти Фотошоп", "Открой Блокнот",
    "Поставь таймер на пять минут",
    "Напомни через десять минут выключить чайник",
    "Какая погода будет завтра", "Что ты умеешь", "Сделай погромче",
    "Найди в интернете рецепт блинов", "Открой Ютуб",
    "Запусти Вижуал Студио Код", "Выключи компьютер через час",
    "Сколько сейчас времени", "Рина, открой проводник",
]

#: The Latin spellings a model may choose for a name said in Russian. Both
#: are the name heard: the matcher takes either.
LATIN = {
    "visual studio code": "вижуал студио код", "google chrome": "гугл хром",
    "google": "гугл", "chrome": "хром", "steam": "стим",
    "telegram": "телеграм", "discord": "дискорд", "spotify": "спотифай",
    "obsidian": "обсидиан", "photoshop": "фотошоп", "youtube": "ютуб",
}
NAMES = ["стим", "телеграм", "дискорд", "хром", "спотифай", "обсидиан",
         "фотошоп", "ютуб", "вижуал студио код", "блокнот", "проводник"]

WINDOWS_VOICES = r'''
param([string]$Phrases, [string]$Out)
$ErrorActionPreference = "Stop"
$lines = Get-Content -Encoding UTF8 $Phrases
Add-Type -AssemblyName System.Speech
$sapi = New-Object System.Speech.Synthesis.SpeechSynthesizer
$sapi.SelectVoice("Microsoft Irina Desktop")
for ($i = 0; $i -lt $lines.Count; $i++) {
    $sapi.SetOutputToWaveFile((Join-Path $Out ("sapi-irina_{0:D2}.wav" -f $i)))
    $sapi.Speak($lines[$i])
}
$sapi.SetOutputToNull(); $sapi.Dispose()
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Media.SpeechSynthesis.SpeechSynthesizer, Windows.Media.SpeechSynthesis, ContentType = WindowsRuntime]
$null = [Windows.Storage.Streams.DataReader, Windows.Storage.Streams, ContentType = WindowsRuntime]
$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($op, [Type]$type) {
    $task = $asTask.MakeGenericMethod($type).Invoke($null, @($op)); $task.Wait() | Out-Null; $task.Result
}
$synth = New-Object Windows.Media.SpeechSynthesis.SpeechSynthesizer
foreach ($name in @("Irina", "Pavel")) {
    $voice = [Windows.Media.SpeechSynthesis.SpeechSynthesizer]::AllVoices |
        Where-Object { $_.DisplayName -like "*$name*" -and $_.Language -eq "ru-RU" } | Select-Object -First 1
    if (-not $voice) { continue }
    $synth.Voice = $voice
    for ($i = 0; $i -lt $lines.Count; $i++) {
        $stream = Await ($synth.SynthesizeTextToStreamAsync($lines[$i])) ([Windows.Media.SpeechSynthesis.SpeechSynthesisStream])
        $size = [uint32]$stream.Size
        $reader = New-Object Windows.Storage.Streams.DataReader($stream.GetInputStreamAt(0))
        $null = Await ($reader.LoadAsync($size)) ([uint32])
        $bytes = New-Object byte[] $size; $reader.ReadBytes($bytes)
        [IO.File]::WriteAllBytes((Join-Path $Out ("onecore-{0}_{1:D2}.wav" -f $name.ToLower(), $i)), $bytes)
    }
}
'''


# ---------------------------------------------------------------------------
# The corpus
# ---------------------------------------------------------------------------
def _resample(x, rate):
    import numpy as np

    if rate == RATE:
        return x
    if rate > RATE:
        step = int(round(rate / RATE))
        if step > 1:
            x = np.convolve(x, np.ones(step) / step, mode="same")
    count = int(len(x) * RATE / rate)
    return np.interp(np.linspace(0, len(x) - 1, count), np.arange(len(x)), x)


def _shape(x, rng):
    """As the segmenter hands a phrase over: run-up, release, a room."""
    import numpy as np

    loud = np.flatnonzero(np.abs(x) > 0.01)
    if len(loud):
        x = x[loud[0]:loud[-1] + 1]
    x = x / (np.max(np.abs(x)) + 1e-9) * rng.uniform(0.25, 0.6)
    x = np.concatenate([np.zeros(int(LEAD * RATE)), x,
                        np.zeros(int(TAIL * RATE))])
    return np.clip(x + _room(len(x), 0.004, rng), -1, 1)


def _room(count, level, rng):
    import numpy as np

    room = np.convolve(rng.normal(0, 1, count), np.ones(8) / 8, mode="same")
    return room * level / (np.std(room) + 1e-9)


def _save(name, x, text, kind, voice):
    import numpy as np

    with wave.open(os.path.join(CORPUS, name + ".wav"), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(RATE)
        out.writeframes((x * 32767).astype(np.int16).tobytes())
    return {"file": name + ".wav", "text": text, "kind": kind, "voice": voice}


def build():
    import numpy as np
    import soundfile

    rng = np.random.default_rng(7)
    raw = os.path.join(HERE, "raw")
    os.makedirs(raw, exist_ok=True)
    os.makedirs(CORPUS, exist_ok=True)
    phrases = os.path.join(HERE, "phrases.txt")
    io.open(phrases, "w", encoding="utf-8").write("\n".join(PHRASES) + "\n")

    script = os.path.join(tempfile.gettempdir(), "rina-hearing-voices.ps1")
    io.open(script, "w", encoding="utf-8-sig").write(WINDOWS_VOICES)
    subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                    "-File", script, "-Phrases", phrases, "-Out", raw], check=True)

    piper = os.path.join(CACHE, "cloud-result", "rina-4692.onnx")
    if os.path.exists(piper):
        from piper import PiperVoice

        voice = PiperVoice.load(piper)
        for at, text in enumerate(PHRASES):
            chunks = list(voice.synthesize(text))
            soundfile.write(os.path.join(raw, f"piper-rina_{at:02d}.wav"),
                            np.concatenate([c.audio_float_array for c in chunks]),
                            chunks[0].sample_rate)

    items = []
    for name in sorted(os.listdir(raw)):
        speaker, at = name[:-4].rsplit("_", 1)
        data, rate = soundfile.read(os.path.join(raw, name), dtype="float32",
                                    always_2d=True)
        x = _resample(data.mean(axis=1).astype(np.float64), rate)
        items.append(_save(f"cmd_{speaker}_{at}", _shape(x, rng),
                           PHRASES[int(at)], "command", speaker))

    sources = os.path.join(CACHE, "sources")
    listed = os.path.join(CACHE, "cv_ru_dev.tsv")
    if os.path.isdir(sources) and os.path.exists(listed):
        wanted = {f.split("__")[-1]: f for f in os.listdir(sources)}
        for row in csv.DictReader(io.open(listed, encoding="utf-8"),
                                  delimiter="\t"):
            if row["path"] not in wanted:
                continue
            data, rate = soundfile.read(os.path.join(sources, wanted[row["path"]]),
                                        dtype="float32", always_2d=True)
            x = _resample(data.mean(axis=1).astype(np.float64), rate)
            items.append(_save("cv_" + row["path"][:-4], _shape(x, rng),
                               row["sentence"], "sentence", row["client_id"][:10]))

    # Nobody speaking, loud enough to cross the segmenter's threshold:
    # anything recognised here is invented, and hints are what a model
    # invents from.
    for at in range(16):
        count = int(rng.uniform(1.5, 3.0) * RATE)
        room = _room(count, [0.004, 0.01, 0.02, 0.04][at % 4], rng)
        if at % 2:
            for click in rng.integers(0, count - 200, 12):
                room[click:click + 200] += (rng.normal(0, 0.15, 200)
                                            * np.hanning(200))
        items.append(_save(f"noise_{at:02d}", np.clip(room, -1, 1), "",
                           "noise", "room"))

    json.dump(items, io.open(os.path.join(CORPUS, "index.json"), "w",
                             encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"клипов {len(items)}: команд "
          f"{sum(i['kind'] == 'command' for i in items)}, фраз "
          f"{sum(i['kind'] == 'sentence' for i in items)}, шума "
          f"{sum(i['kind'] == 'noise' for i in items)}")


# ---------------------------------------------------------------------------
# The measurement
# ---------------------------------------------------------------------------
def norm(text):
    from voice.textmatch import normalize

    said = normalize(text)
    for latin, cyrillic in LATIN.items():
        said = said.replace(latin, cyrillic)
    return " ".join({"5": "пять", "10": "десять"}.get(w, w) for w in said.split())


def cer(ref, hyp):
    before = list(range(len(hyp) + 1))
    for i, a in enumerate(ref, 1):
        now = [i]
        for j, b in enumerate(hyp, 1):
            now.append(min(before[j] + 1, now[j - 1] + 1,
                           before[j - 1] + (a != b)))
        before = now
    return before[-1] / max(1, len(ref))


def installed():
    """This machine's programs, as the shell last wrote them down."""
    from core.apps import AppEntry
    from core.settings_store import config_dir

    path = os.path.join(config_dir(), "app_index.json")
    try:
        data = json.load(io.open(path, encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [AppEntry(e.get("Name", ""), e.get("Launch", ""),
                     e.get("Kind", "file"), e.get("Source", "start_menu"))
            for e in data.get("Entries", [])]


def configurations(index):
    from core import apps, speech
    from core.settings_api import MemorySettings

    line = ", ".join(apps.spoken_hints(index, ("Рина",)))

    def program(size="base", hints=True):
        ear = speech.whisper_for(MemorySettings({"whisper_model": size}),
                                 hints=(lambda: line) if hints else None)
        return lambda pcm: ear.recognise(pcm).text

    def as_in_3_1():
        import numpy as np
        import whisper

        model = whisper.load_model("base")

        def run(pcm):
            x = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768
            return str(model.transcribe(x, language="ru", fp16=False)["text"])
        return run

    return {
        "программа (base, подсказки)": lambda: program(),
        "без подсказок": lambda: program(hints=False),
        "small, подсказки": lambda: program("small"),
        "как в 3.1 (openai-whisper)": as_in_3_1,
    }


def launches(said, text, index):
    from voice import app_launcher

    decision = app_launcher.decide(said, apps=index)
    if decision is None or decision.entry is None:
        return False
    want = {"стим": "steam", "телеграм": "telegram", "обсидиан": "obsidian",
            "блокнот": "notepad|блокнот", "вижуал студио код": "visual studio code",
            "проводник": "explorer|проводник", "дискорд": "discord",
            "хром": "chrome", "спотифай": "spotify", "фотошоп": "photoshop"}
    name = decision.entry.name.lower()
    return any(any(w in name for w in target.split("|"))
               for spoken, target in want.items() if spoken in norm(text))


def run(wanted):
    from core import apps

    items = json.load(io.open(os.path.join(CORPUS, "index.json"), encoding="utf-8"))
    index = installed()
    # Installed by the rule the hints use, not by `find`: `find` lets a
    # helper from PATH answer for a name, and the first run counted Chrome
    # as installed here on the strength of `codex-chrome-native-host`.
    present = {norm(name) for name in apps.spoken_hints(index)}
    here = [i for i in items if i["kind"] == "command"
            and any(n in norm(i["text"]) and n in present for n in NAMES)]
    for title, build_it in configurations(index).items():
        if wanted and not any(w in title for w in wanted):
            continue
        hear = build_it()
        clips = {}
        for item in items:
            with wave.open(os.path.join(CORPUS, item["file"]), "rb") as f:
                clips[item["file"]] = f.readframes(f.getnframes())
        hear(clips[items[0]["file"]])                   # warm, not counted
        said, spent = {}, {}
        for item in items:
            started = time.perf_counter()
            said[item["file"]] = hear(clips[item["file"]])
            spent[item["file"]] = time.perf_counter() - started
        cmd = [i for i in items if i["kind"] == "command"]
        sen = [i for i in items if i["kind"] == "sentence"]
        noise = [i for i in items if i["kind"] == "noise"]
        exact = sum(norm(said[i["file"]]) == norm(i["text"]) for i in cmd)
        named = [i for i in cmd if any(n in norm(i["text"]) for n in NAMES)]
        heard = sum(any(n in norm(i["text"]) and n in norm(said[i["file"]])
                        for n in NAMES) for i in named)
        launched = sum(launches(said[i["file"]], i["text"], index) for i in here)
        wrong = statistics.mean(cer(norm(i["text"]), norm(said[i["file"]]))
                                for i in sen) if sen else 0.0
        invented = sum(bool(norm(said[i["file"]])) for i in noise)
        times = sorted(spent[i["file"]] for i in cmd)
        print(f"{title:30s} команд точно {exact}/{len(cmd)}, имя {heard}/{len(named)}, "
              f"запустилось бы {launched}/{len(here)}, ошибок в фразах {wrong:.1%}, "
              f"выдумано на шуме {invented}/{len(noise)}, "
              f"{statistics.mean(times):.2f} с на фразу", flush=True)


if __name__ == "__main__":
    if sys.argv[1:2] == ["build"]:
        build()
    elif sys.argv[1:2] == ["run"]:
        run(sys.argv[2:])
    else:
        print(__doc__)
