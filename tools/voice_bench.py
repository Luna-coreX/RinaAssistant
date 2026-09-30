# -*- coding: utf-8 -*-
"""
Стенд замеров синтеза речи (задача плана V-02).

Единая методика для V-03: все кандидаты проходят один корпус и меряются
одинаково, иначе сравнение превращается в «мне показалось».

Что меряется механически:
  * TTFA — время до первого звука. Главная продуктовая метрика (5.0-A08):
    разница между «отвечает через 4 секунды» и «начинает говорить через
    400 мс» — это разница между инструментом и собеседником.
  * RTF — отношение времени синтеза к длительности результата. Меньше 1 —
    синтезирует быстрее, чем произносит.
  * Пиковая память видеокарты, если модель её использует.
  * Длительность и частота дискретизации результата.

Что мерится ушами и потому только готовится, а не оценивается:
  * естественность и выразительность,
  * стабильность тембра между репликами.
Стенд раскладывает файлы под слепое сравнение: имена обезличены, соответствие
лежит отдельно (см. --blind).

Добавить кандидата — значит написать адаптер: класс с методом
`synthesize(text, path) -> None` и атрибутом `name`. Адаптеры для движков,
которые уже есть в приложении, лежат ниже и служат опорными точками: без них
непонятно, хорош ли новый кандидат или просто не хуже того, что уже стоит.

Запуск:
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
# Адаптеры
# ---------------------------------------------------------------------------
class Adapter:
    """Кандидат на стенде."""

    name = "?"
    streaming = False        # умеет ли отдавать звук до конца синтеза

    def prepare(self):
        """Загрузка модели. Не входит в замер TTFA."""

    def synthesize(self, text, path):
        raise NotImplementedError

    def unload(self):
        pass


class EdgeAdapter(Adapter):
    """Опорная точка: онлайн-синтез, который приложение уже умеет."""

    name = "edge"
    voice = "ru-RU-SvetlanaNeural"

    def synthesize(self, text, path):
        import asyncio
        import edge_tts

        async def run():
            await edge_tts.Communicate(text, self.voice).save(path)

        asyncio.run(run())


class Pyttsx3Adapter(Adapter):
    """Опорная точка: системный офлайн-синтез, нижняя граница качества."""

    name = "pyttsx3"

    def synthesize(self, text, path):
        import pyttsx3

        engine = pyttsx3.init()
        engine.save_to_file(text, path)
        engine.runAndWait()
        engine.stop()


class PiperAdapter(Adapter):
    """Опорная точка: офлайн-нейро. Нужна модель в настройках приложения."""

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
# Измерения
# ---------------------------------------------------------------------------
def gpu_peak_mb():
    """Пик памяти видеокарты или None, если её не используют."""
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
    """Длительность и частота или (None, None), если файл не читается."""
    try:
        import soundfile as sf

        info = sf.info(path)
        return round(info.duration, 3), info.samplerate
    except Exception:
        # mp3 без поддержки в soundfile — оцениваем только размер
        return None, None


def measure(adapter, item, out_dir):
    """Один замер: синтез одной фразы."""
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
    size = os.path.getsize(path) if os.path.isfile(path) else 0

    return {
        "id": item["id"],
        "group": item["group"],
        "chars": len(item["text"]),
        # Без потокового синтеза первый звук доступен только когда готово всё,
        # поэтому TTFA равен полному времени. У потокового кандидата адаптер
        # обязан замерить момент первого чанка и переопределить это поле.
        "ttfa_s": None if error else round(elapsed, 3),
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
# Слепое сравнение
# ---------------------------------------------------------------------------
def make_blind(run_dir):
    """
    Раскладывает записи под слепое прослушивание: имена обезличены,
    соответствие лежит рядом отдельным файлом.

    Смысл: услышав имя движка, оценивают имя, а не звук.
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

        # Прогрев. Первый синтез у каждого движка втрое дороже остальных:
        # у сетевого это установка соединения, у локального — инициализация.
        # Без него первая фраза корпуса штрафуется за то, что она первая,
        # и медиана съезжает.
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
