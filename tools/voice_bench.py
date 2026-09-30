# -*- coding: utf-8 -*-
"""
A bench for measuring speech synthesis (plan item V-02).

One method for V-03: every candidate goes through one corpus and is measured
the same way, or the comparison turns into "it seemed to me".

What is measured mechanically:
  * TTFA — the time to the first sound. The main product metric (5.0-A08):
    the difference between "answers in 4 seconds" and "starts speaking in
    400 ms" is the difference between an instrument and an interlocutor.
  * RTF — the ratio of the synthesis time to the result's duration. Below 1
    means it synthesises faster than it says.
  * The graphics card's peak memory, if the model uses it.
  * The result's duration and sample rate.

What is measured by ear and so is only prepared rather than judged:
  * naturalness and expressiveness,
  * the timbre's stability between lines.
The bench lays the files out for a blind comparison: the names are made
anonymous and the mapping lies separately (see --blind).

Adding a candidate means writing an adapter: a class with a
`synthesize(text, path) -> None` method and a `name` attribute. The adapters
for the engines already in the application are below and serve as reference
points: without them it is unclear whether a new candidate is good or merely
no worse than what is already installed.

To run:
    python tools/voice_bench.py --engines edge,pyttsx3
    python tools/voice_bench.py --engines edge --groups short,numbers
    python tools/voice_bench.py --blind out/run-2026-09-01
"""

import argparse
import json
import os
import random
import shutil
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

CORPUS = os.path.join(ROOT, "docs", "voice", "corpus.json")
OUT_ROOT = os.path.join(ROOT, "out", "voice-bench")


# ---------------------------------------------------------------------------
# The adapters
# ---------------------------------------------------------------------------
class Adapter:
    """A candidate on the bench."""

    name = "?"
    streaming = False        # can it give out sound before synthesis ends

    def prepare(self):
        """Loading the model. Not part of the TTFA measurement."""

    def synthesize(self, text, path):
        raise NotImplementedError

    def unload(self):
        pass


class EdgeAdapter(Adapter):
    """A reference point: online synthesis, which the application already has.

    **Through the application's own engine, not through `edge-tts`
    directly.** The other adapters here are candidates the program does
    not have yet, and for them the library is the only thing to call.
    Edge is the one the program ships, and the sentence above is its
    whole reason for being on the bench — so measuring anything other
    than the path the program actually takes makes the reference point
    a reference to nothing.

    It mattered. This adapter called `Communicate.save()`, which waits
    out the whole reply, and went on doing so after `4.0b-E10` taught
    Edge to stream. The bench reported the main product metric for the
    one engine people use as 1447 ms when the program was managing
    1027: a measurement that kept its name after its subject moved.
    """

    name = "edge"
    voice = "ru-RU-SvetlanaNeural"
    streaming = True

    #: When the first sound was ready, and how much sound came out.
    #: Both are filled in during `synthesize` and read by `measure`.
    first_at = None
    audio_s = None

    def synthesize(self, text, path):
        from core.speech import pcm_from_stream
        from voice import tts

        engine = tts.get_engine("edge")
        self.first_at = None
        self.audio_s = None
        started = time.perf_counter()
        samples = 0
        hertz = 0

        with open(path, "wb") as into:
            def passing():
                # The chunks go to disk on their way through, so the
                # blind comparison still gets its file: the point of
                # streaming is that nothing waits for the file, not
                # that there is no file.
                for chunk in engine.stream(text, volume=75, rate=100):
                    if chunk:
                        into.write(chunk)
                        yield chunk

            for pcm, rate in pcm_from_stream(passing(), engine.stream_format):
                if not pcm:
                    continue
                if self.first_at is None:
                    # Measured at the first **decoded** sample, not at
                    # the first mp3 chunk. What the program can play is
                    # the honest "first sound"; the raw chunk is a
                    # promise of one, and counting it would flatter
                    # this engine against the others by the decoding.
                    self.first_at = time.perf_counter() - started
                samples += len(pcm) // 2
                hertz = rate or hertz

        if samples and hertz:
            self.audio_s = round(samples / hertz, 3)


class Pyttsx3Adapter(Adapter):
    """A reference point: system offline synthesis, the lower bound of quality."""

    name = "pyttsx3"

    def synthesize(self, text, path):
        import pyttsx3

        engine = pyttsx3.init()
        engine.save_to_file(text, path)
        engine.runAndWait()
        engine.stop()


class PiperAdapter(Adapter):
    """A reference point: offline neural. Needs a model in the application's settings."""

    name = "piper"

    def prepare(self):
        from core.settings_store import settings
        from piper import PiperVoice

        settings.load()
        model = settings.get("piper_model", "")
        if not model or not os.path.isfile(model):
            raise RuntimeError("модель Piper не выбрана в настройках")
        self._voice = PiperVoice.load(model)

    def synthesize(self, text, path):
        import wave

        with wave.open(path, "wb") as wav:
            if hasattr(self._voice, "synthesize_wav"):
                self._voice.synthesize_wav(text, wav)
            else:
                self._voice.synthesize(text, wav)


ADAPTERS = {a.name: a for a in (EdgeAdapter, Pyttsx3Adapter, PiperAdapter)}


# ---------------------------------------------------------------------------
# The measurements
# ---------------------------------------------------------------------------
def gpu_peak_mb():
    """The graphics card's peak memory, or None if it is not used."""
    try:
        import torch

        if not torch.cuda.is_available():
            return None
        return round(torch.cuda.max_memory_allocated() / (1024 * 1024), 1)
    except Exception:
        return None


def gpu_reset():
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.reset_peak_memory_stats()
    except Exception:
        pass


def audio_facts(path):
    """The duration and the rate, or (None, None) if the file cannot be read."""
    try:
        import soundfile as sf

        info = sf.info(path)
        return round(info.duration, 3), info.samplerate
    except Exception:
        # an mp3 unsupported by soundfile — we judge only by size
        return None, None


def measure(adapter, item, out_dir):
    """One measurement: synthesising one phrase."""
    path = os.path.join(out_dir, f"{adapter.name}__{item['id']}.wav")
    if isinstance(adapter, EdgeAdapter):
        path = path[:-4] + ".mp3"

    gpu_reset()
    started = time.perf_counter()
    error = None
    try:
        adapter.synthesize(item["text"], path)
    except Exception as e:
        error = f"{type(e).__name__}: {e}"
    elapsed = time.perf_counter() - started

    duration, rate = audio_facts(path) if error is None else (None, None)
    # An mp3 `soundfile` cannot read still has a duration if the adapter
    # decoded it on the way past. Without this Edge had no RTF at all —
    # a dash in the column that decides whether a voice keeps up with
    # itself.
    if duration is None and getattr(adapter, "audio_s", None):
        duration = adapter.audio_s
    size = os.path.getsize(path) if os.path.isfile(path) else 0

    # Without streaming the first sound is available only once everything
    # is ready, so TTFA equals the whole time. A streaming adapter says
    # when its first sound was actually there, and that is the number
    # this bench exists to compare.
    ttfa = elapsed
    if getattr(adapter, "streaming", False):
        ttfa = getattr(adapter, "first_at", None)

    return {
        "id": item["id"],
        "group": item["group"],
        "chars": len(item["text"]),
        "ttfa_s": None if error or ttfa is None else round(ttfa, 3),
        "synthesis_s": round(elapsed, 3),
        "audio_s": duration,
        "rtf": round(elapsed / duration, 3) if duration else None,
        "samplerate": rate,
        "bytes": size,
        "gpu_peak_mb": gpu_peak_mb(),
        "file": os.path.relpath(path, ROOT),
        "error": error,
    }


def summarize(rows):
    ok = [r for r in rows if not r["error"]]
    if not ok:
        return {"cases": len(rows), "ok": 0}
    ttfa = sorted(r["ttfa_s"] for r in ok if r["ttfa_s"] is not None)
    rtfs = [r["rtf"] for r in ok if r["rtf"]]

    def pct(values, p):
        if not values:
            return None
        return values[min(len(values) - 1, int(len(values) * p))]

    short = [r["ttfa_s"] for r in ok if r["group"] == "short" and r["ttfa_s"]]
    return {
        "cases": len(rows),
        "ok": len(ok),
        "failed": len(rows) - len(ok),
        "ttfa_median_s": pct(ttfa, 0.5),
        "ttfa_p90_s": pct(ttfa, 0.9),
        "ttfa_short_median_s": round(sum(short) / len(short), 3) if short else None,
        "rtf_median": pct(sorted(rtfs), 0.5) if rtfs else None,
        "gpu_peak_mb": max((r["gpu_peak_mb"] or 0) for r in ok) or None,
    }


# ---------------------------------------------------------------------------
# The blind comparison
# ---------------------------------------------------------------------------
def make_blind(run_dir):
    """
    Lays the recordings out for blind listening: the names are made
    anonymous and the mapping lies beside them in a separate file.

    The point: hearing an engine's name, one judges the name rather than the
    sound.
    """
    report = json.load(open(os.path.join(run_dir, "report.json"),
                          encoding="utf-8"))
    blind_dir = os.path.join(run_dir, "blind")
    os.makedirs(blind_dir, exist_ok=True)

    pairs = []
    for engine, data in report["engines"].items():
        for row in data["rows"]:
            if not row["error"] and os.path.isfile(os.path.join(ROOT, row["file"])):
                pairs.append((engine, row))

    random.shuffle(pairs)
    key = []
    for i, (engine, row) in enumerate(pairs, 1):
        ext = os.path.splitext(row["file"])[1]
        name = f"{i:03d}{ext}"
        shutil.copy2(os.path.join(ROOT, row["file"]),
                     os.path.join(blind_dir, name))
        key.append({"file": name, "engine": engine, "id": row["id"],
                    "group": row["group"]})

    with open(os.path.join(run_dir, "blind-key.json"), "w",
              encoding="utf-8") as f:
        json.dump(key, f, ensure_ascii=False, indent=2)

    sheet = os.path.join(run_dir, "blind-sheet.md")
    with open(sheet, "w", encoding="utf-8") as f:
        f.write("# Слепое прослушивание\n\n")
        f.write("Оценки от 1 до 5. Ключ не открывать до конца.\n\n")
        f.write("| Файл | Естественность | Выразительность | Тот же голос? | Заметки |\n")
        f.write("|---|---|---|---|---|\n")
        for row in key:
            f.write(f"| {row['file']} |  |  |  |  |\n")
    print(f"  слепой набор: {len(key)} записей -> {blind_dir}")
    print(f"  бланк оценок: {os.path.relpath(sheet, ROOT)}")
    print(f"  ключ (не открывать заранее): blind-key.json")


# ---------------------------------------------------------------------------
def run(engine_names, groups, run_dir):
    corpus = json.load(open(CORPUS, encoding="utf-8"))
    items = corpus["items"]
    if groups:
        items = [i for i in items if i["group"] in groups]

    os.makedirs(run_dir, exist_ok=True)
    report = {"corpus": os.path.relpath(CORPUS, ROOT),
              "items": len(items), "engines": {}}

    for name in engine_names:
        cls = ADAPTERS.get(name)
        if cls is None:
            print(f"{name}: неизвестный движок, пропускаю")
            continue
        adapter = cls()
        print(f"\n=== {name} ===")
        try:
            adapter.prepare()
        except Exception as e:
            print(f"  не готов: {e}")
            report["engines"][name] = {"unavailable": str(e), "rows": []}
            continue

        # A warm-up. Every engine's first synthesis costs three times the
        # rest: for a network one that is establishing a connection, for a
        # local one initialisation. Without it the corpus's first phrase is
        # penalised for being first, and the median shifts.
        warmup = {"id": "__warmup__", "group": "warmup",
                  "text": "Проверка связи."}
        warm = measure(adapter, warmup, run_dir)
        print(f"     прогрев (не в зачёт)   {warm['synthesis_s']:6.3f}s")

        rows = []
        for item in items:
            row = measure(adapter, item, run_dir)
            rows.append(row)
            mark = "  " if not row["error"] else "!!"
            ttfa = f"{row['ttfa_s']:6.3f}s" if row["ttfa_s"] else "   —   "
            print(f"  {mark} {row['id']:<20} {ttfa}"
                  + (f"  {row['error']}" if row["error"] else ""))
        adapter.unload()

        stats = summarize(rows)
        report["engines"][name] = {"summary": stats, "rows": rows}
        print(f"  --- TTFA медиана {stats.get('ttfa_median_s')}s, "
              f"короткие {stats.get('ttfa_short_median_s')}s, "
              f"RTF {stats.get('rtf_median')}, "
              f"сбоев {stats.get('failed')}")

    with open(os.path.join(run_dir, "report.json"), "w",
              encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\nОтчёт: {os.path.relpath(os.path.join(run_dir, 'report.json'), ROOT)}")
    return report


def main():
    ap = argparse.ArgumentParser(description="Стенд замеров синтеза речи")
    ap.add_argument("--engines", default="edge",
                    help="через запятую: " + ", ".join(ADAPTERS))
    ap.add_argument("--groups", default="",
                    help="группы корпуса через запятую (пусто — все)")
    ap.add_argument("--blind", metavar="RUN_DIR",
                    help="разложить готовый прогон под слепое сравнение")
    args = ap.parse_args()

    if args.blind:
        make_blind(args.blind)
        return 0

    stamp = time.strftime("%Y-%m-%d_%H-%M-%S")
    run_dir = os.path.join(OUT_ROOT, stamp)
    groups = [g.strip() for g in args.groups.split(",") if g.strip()]
    run([e.strip() for e in args.engines.split(",") if e.strip()],
        groups, run_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
