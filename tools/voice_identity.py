# -*- coding: utf-8 -*-
"""
Whose voice is this, measured rather than claimed (plan item `V-03`).

ADR 0003 decided that Rina's voice is a synthesised speaker vector
belonging to no real person, and attached a condition to the decision:
"«Belongs to nobody» is a claim, and a claim needs a check." This is
the check.

**The measurement is deliberately made outside the model being
judged.** Every synthesiser has its own speaker space, and a cosine
inside it means whatever that model was trained to mean — the numbers
are not comparable between candidates, and a model that hides the
speaker inside token quantisation has no such space at all. So the
distance is measured on the **sound**: the synthesised audio goes
through a speaker-verification network that knows nothing about the
synthesiser, and the cosine is taken there. That space exists for
exactly one question — "is this the same person" — and it answers it
the same way for every candidate that can produce a wav.

It mattered on the first model measured. Interpolating halfway between
the two speakers of a VITS table gave, in the model's own space, a
symmetric 0.904 / 0.902 — a vector apparently equidistant from both.
By sound it was 0.844 to one speaker and 0.645 to the other: not a new
person standing between them but the first speaker, slightly shifted.

To run:
    python tools/voice_identity.py --sweep
    python tools/voice_identity.py --check some/dir/*.wav --against ref.wav
"""

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

OUT_ROOT = os.path.join(ROOT, "out", "voice-identity")

#: Where the verification model is kept. Beside the application's own
#: data rather than in the repository: it is 25 MB of somebody else's
#: weights, and a check's dependency is not a project asset.
CACHE = os.path.join(os.path.expanduser("~"), ".cache", "rina-voice")

#: The verification network.
#:
#: CAM++ from 3D-Speaker, trained on Chinese and English common data:
#: 27 MB, Apache-2.0, runs on the processor in ONNX.
#:
#: **Chosen by measurement, after the obvious choice failed.** The first
#: network here was WeSpeaker ResNet34 on VoxCeleb, a field standard,
#: and on two VITS speakers — a man and a woman — it separated cleanly.
#: On eight adult women recorded through consumer microphones it stopped
#: working: different people averaged 0.647 and the closest pair reached
#: 0.880, while a control that was certainly the same voice scored
#: 0.861. The gap was **negative** — the same person scored lower than
#: the most similar two strangers — and every identity number taken with
#: it was undecidable.
#:
#: Reaching for a bigger model of the same family did not help:
#: ResNet293, four times the size, gave +0.006. The problem was the
#: domain, not the capacity. CAM++ on the same recordings: different
#: people 0.308, closest pair 0.537, same person 0.856 — a gap of
#: +0.319.
#:
#: The lesson is kept beside the constant: speaker verification is
#: called language-independent, and across a homogeneous cohort in a
#: language the network never heard, it is not. Whichever network stands
#: here, `check()` prints the cohort's own spread, so a verifier that
#: has stopped separating says so instead of returning a number anyway.
VERIFIER = "3dspeaker_speech_campplus_sv_zh_en_16k-common_advanced.onnx"
VERIFIER_URL = ("https://huggingface.co/csukuangfj/speaker-embedding-models/"
                "resolve/main/" + VERIFIER)

#: A starting threshold only, and not to be trusted on its own.
#:
#: **A fixed number was wrong the first time it met a real cohort.**
#: Against two VITS speakers — a man and a woman — the scale was clean:
#: 0.97 for the same voice, 0.62 between the two. Against eight adult
#: women recorded on consumer microphones, the same network put two
#: *different* people at 0.880 and averaged 0.647, while a control that
#: was certainly the same voice scored 0.888. Nothing could be decided
#: at those numbers, and a check reading 0.60 would have decided
#: anyway.
#:
#: So the cohort calibrates the threshold: `spread()` measures how far
#: apart the reference speakers are from each other, and a candidate is
#: judged against that, not against this constant. The constant stays
#: as the fallback for when there is only one reference to compare to.
SAME_PERSON = 0.60

#: Phrases for judging identity.
#:
#: Rina's own lines, for the same reason `docs/voice/corpus.json` is
#: made of them: a timbre that holds on an invented paragraph and comes
#: apart on "Visual Studio Code" is a timbre this product cannot use.
#: Several of them, because one phrase is too little sound for a
#: verification network to be sure of.
PHRASES = (
    "Привет. Я Рина, и это мой собственный голос.",
    "Готово. Открываю Visual Studio Code.",
    "Напоминаю: встреча с друзьями в восемнадцать ноль-ноль.",
)


#: Others measured on the way, kept so the comparison can be repeated.
OTHER_VERIFIERS = ("wespeaker_en_voxceleb_resnet34_LM.onnx",
                   "wespeaker_en_voxceleb_resnet293_LM.onnx")


def verifier_path(quiet=False):
    """The verification model, fetched once if it is not here yet."""
    import urllib.request

    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, VERIFIER)
    if not os.path.isfile(path):
        if not quiet:
            print("Скачиваю сеть верификации диктора (~25 МБ):")
            print("   ", VERIFIER_URL)
        urllib.request.urlretrieve(VERIFIER_URL, path)
    return path


class Verifier:
    """Somebody else's ears: an embedding per recording, and a cosine."""

    def __init__(self):
        import sherpa_onnx

        self._ex = sherpa_onnx.SpeakerEmbeddingExtractor(
            sherpa_onnx.SpeakerEmbeddingExtractorConfig(
                model=verifier_path(), num_threads=4))

    @property
    def dim(self):
        return self._ex.dim

    def embed(self, wave, rate):
        import numpy as np

        stream = self._ex.create_stream()
        stream.accept_waveform(rate, wave)
        stream.input_finished()
        return np.array(self._ex.compute(stream), dtype=np.float32)

    def embed_file(self, path):
        import soundfile as sf

        wave, rate = sf.read(path, dtype="float32")
        if wave.ndim > 1:
            wave = wave.mean(axis=1)
        return self.embed(wave, rate)


def cosine(a, b):
    import numpy as np

    return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b)))


# ---------------------------------------------------------------------------
# The VITS speaker table
# ---------------------------------------------------------------------------
#: A multi-speaker Russian VITS, Apache-2.0, 15.1 M parameters, 16 kHz.
#:
#: Chosen because its speaker table is an ordinary embedding matrix
#: whose rows can simply be added — ADR 0003 satisfied literally and for
#: free. Its weakness is known before any measurement: it has two
#: speakers, and two points make a segment, not a space.
VITS_MODEL = "utrobinmv/tts_ru_free_hf_vits_low_multispeaker"


class VitsVoices:
    """A VITS whose speaker table has one extra row we may write into."""

    def __init__(self, name=VITS_MODEL):
        import torch
        from transformers import AutoTokenizer, VitsModel

        self._torch = torch
        self.model = VitsModel.from_pretrained(name).eval()
        self.tok = AutoTokenizer.from_pretrained(name)
        self.rate = self.model.config.sampling_rate

        table = self.model.embed_speaker.weight.detach().clone()
        self.speakers = table
        self.slot = table.shape[0]
        # A row of our own on the end. The alternative — replacing a real
        # speaker's row — would destroy the very reference the check
        # compares against.
        bigger = torch.nn.Embedding(self.slot + 1, table.shape[1])
        bigger.weight.data[:self.slot] = table
        self.model.embed_speaker = bigger
        # The forward pass validates the id against the config, so the
        # config has to know about the new row too.
        self.model.config.num_speakers = self.slot + 1

    def say(self, vector, phrases=PHRASES):
        """Synthesise the phrases with this speaker vector; one waveform."""
        import numpy as np

        self.model.embed_speaker.weight.data[self.slot] = vector
        parts = []
        for text in phrases:
            ins = self.tok(text, return_tensors="pt")
            with self._torch.no_grad():
                parts.append(self.model(**ins, speaker_id=self.slot)
                             .waveform[0].numpy())
        return np.concatenate(parts).astype(np.float32)

    def mix(self, alpha, first=0, second=1):
        """A vector on the line through two speakers. Outside [0,1] too."""
        return (1 - alpha) * self.speakers[first] + alpha * self.speakers[second]


def sweep(alphas, out_dir):
    """Walk the line between two speakers and ask who is speaking."""
    import soundfile as sf

    os.makedirs(out_dir, exist_ok=True)
    voices = VitsVoices()
    ears = Verifier()
    print(f"Синтез: {VITS_MODEL}, {voices.rate} Гц, "
          f"говорящих {voices.slot}")
    print(f"Верификатор: {VERIFIER}, размерность {ears.dim}")
    print()

    # The reference recordings are the model's own renderings of its two
    # speakers, not the humans behind them. That is the right question:
    # not "does this sound like the person who was recorded" but "does
    # this sound like a voice this model already has".
    refs = []
    for at in range(voices.slot):
        wave = voices.say(voices.speakers[at])
        sf.write(os.path.join(out_dir, f"speaker_{at}.wav"), wave, voices.rate)
        refs.append(ears.embed(wave, voices.rate))

    between = cosine(refs[0], refs[1])
    print(f"Два живых диктора отстоят друг от друга на {between:.4f}")
    print()
    print("  α        до 0     до 1      макс    громкость")

    rows = []
    for alpha in alphas:
        wave = voices.say(voices.mix(alpha))
        name = "mix_%+05.2f.wav" % alpha
        sf.write(os.path.join(out_dir, name), wave, voices.rate)
        mine = ears.embed(wave, voices.rate)
        near = [cosine(mine, one) for one in refs]
        worst = max(near)
        import numpy as np

        loud = float(np.sqrt(np.mean(wave ** 2)))
        mark = "   ← ничей" if worst < SAME_PERSON else ""
        print("  %+5.2f    %.4f   %.4f    %.4f    %.4f%s"
              % (alpha, near[0], near[1], worst, loud, mark))
        rows.append({"alpha": alpha, "nearest": worst, "to": near,
                     "rms": loud, "file": name})

    print()
    best = min(rows, key=lambda r: r["nearest"])
    print("Ближе всего к «ничей» — α=%+.2f, и там %.4f при пороге %.2f."
          % (best["alpha"], best["nearest"], SAME_PERSON))
    if best["nearest"] >= SAME_PERSON:
        print("То есть ни одна точка прямой не даёт нового человека:")
        print("голос садится на одного из двух дикторов везде, включая")
        print("продолжение прямой за оба конца.")
    print()
    print("Записи:", os.path.relpath(out_dir, ROOT))
    return rows


def spread(refs):
    """How far this cohort's own speakers stand from each other.

    The scale of the answer, measured on the very people the candidate
    is compared against, rather than taken from a constant: eight women
    of similar age recorded on similar microphones sit far closer
    together than a man and a woman do, and the same number means
    different things in the two cases.
    """
    import itertools

    names = list(refs)
    pairs = [cosine(refs[a], refs[b])
             for a, b in itertools.combinations(names, 2)]
    if not pairs:
        return None
    return {"n": len(names), "mean": sum(pairs) / len(pairs),
            "min": min(pairs), "max": max(pairs)}


def check(paths, against, out=None):
    """The ADR 0003 check on any recordings: how near are they to each other."""
    ears = Verifier()
    mine = {os.path.basename(p): ears.embed_file(p) for p in paths}
    refs = {os.path.basename(p): ears.embed_file(p) for p in against}
    print(f"Верификатор: {VERIFIER}, размерность {ears.dim}")

    scale = spread(refs)
    if scale:
        print("Разброс самих источников (%d шт.): среднее %.4f, "
              "от %.4f до %.4f"
              % (scale["n"], scale["mean"], scale["min"], scale["max"]))
        bar = scale["max"]
        print("Планка «дальше всех» — %.4f: столько набирают самые "
              "похожие двое из них." % bar)
        if bar > 0.70:
            # Said out loud, because a check that cannot separate is
            # worse than no check: it returns a number either way.
            print("ВНИМАНИЕ: источники плохо различимы этим "
                  "верификатором — на таких числах решать нельзя.")
    else:
        bar = SAME_PERSON
        print("Источник один: сравниваю с запасным порогом %.2f" % bar)
    print()

    for name, vector in mine.items():
        near = [(cosine(vector, one), who) for who, one in refs.items()]
        near.sort(reverse=True)
        worst, who = near[0]
        # Stated as what was actually measured. The bar is the closest
        # pair among the sources, so falling below it means only that
        # two real people are at least this alike — a weak claim, and
        # the strongest this comparison supports.
        verdict = ("не ближе, чем самые похожие двое источников"
                   if worst < bar
                   else "ближе к %s, чем любые двое источников" % who)
        print("  %-34s ближайший %.4f (%s) — %s" % (name, worst, who, verdict))


def pick(folder, canonical, into, keep=0.7, least=None):
    """Keep the takes that still sound like the canonical sample.

    **Generated material drifts, and the drift is a selection problem
    rather than a defect.** A voice pinned by its own recording holds
    at about 0.758 across utterances where the same person scores
    0.856: recognisably one person, and loose enough that training a
    voice conversion model on all of it would teach the average of the
    wandering. There is a measure of how far each take has wandered,
    so the loosest ones are simply not used.

    Ranked rather than thresholded: a threshold is a number chosen
    before seeing the distribution, and this one would have to be
    chosen again for every voice.
    """
    import shutil

    ears = Verifier()
    want = ears.embed_file(canonical)
    takes = sorted(glob_wavs(folder))
    if not takes:
        print("нечего отбирать:", folder)
        return []
    scored = sorted(((cosine(ears.embed_file(p), want), p) for p in takes),
                    reverse=True)
    total = sum(v for v, _ in scored) / len(scored)
    how_many = least if least else max(1, int(len(scored) * keep))
    how_many = min(how_many, len(scored))
    os.makedirs(into, exist_ok=True)
    for _, path in scored[:how_many]:
        shutil.copy2(path, os.path.join(into, os.path.basename(path)))
    print("дублей: %d, среднее до канона %.3f" % (len(scored), total))
    print("оставлено %d: от %.3f до %.3f"
          % (how_many, scored[how_many - 1][0], scored[0][0]))
    print("отброшено %d: от %.3f до %.3f"
          % (len(scored) - how_many,
             scored[-1][0] if len(scored) > how_many else 0.0,
             scored[how_many][0] if len(scored) > how_many else 0.0))
    print("куда:", into)
    return scored[:how_many]


def glob_wavs(folder):
    import glob as _glob

    return _glob.glob(os.path.join(folder, "*.wav"))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sweep", action="store_true",
                    help="пройти прямую между двумя дикторами VITS")
    ap.add_argument("--alphas", default="-0.75,-0.5,-0.25,0,0.25,0.5,"
                                        "0.75,1,1.25,1.5,1.75",
                    help="точки на прямой, через запятую")
    ap.add_argument("--check", nargs="+", metavar="WAV",
                    help="замерить готовые записи")
    ap.add_argument("--against", nargs="+", metavar="WAV", default=(),
                    help="записи живых дикторов для сравнения")
    ap.add_argument("--out", default=None, help="куда класть записи")
    ap.add_argument("--pick", metavar="DIR",
                    help="отобрать дубли, ближайшие к --canonical")
    ap.add_argument("--canonical", metavar="WAV",
                    default=os.path.join(ROOT, "assets", "voice",
                                         "rina-voice-v1.wav"),
                    help="эталонная запись голоса")
    ap.add_argument("--keep", type=float, default=0.7,
                    help="какую долю оставить (0..1)")
    args = ap.parse_args()

    out_dir = args.out or os.path.join(OUT_ROOT, "sweep")
    if args.sweep:
        alphas = [float(x) for x in args.alphas.split(",") if x.strip()]
        sweep(alphas, out_dir)
        return 0
    if args.pick:
        pick(args.pick, args.canonical,
             args.out or os.path.join(OUT_ROOT, "picked"), keep=args.keep)
        return 0
    if args.check:
        if not args.against:
            print("нужен --against: с чем сравнивать")
            return 2
        check(args.check, args.against)
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    from console import use_utf8

    use_utf8()
    sys.exit(main())
