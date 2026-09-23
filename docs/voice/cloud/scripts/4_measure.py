# -*- coding: utf-8 -*-
"""Step 4. Is it still Rina, and is it still nobody.

The same check the whole track was decided by. It asks a speaker
verification network — CAM++ from 3D-Speaker, which separates this
cohort where a VoxCeleb network does not — three questions about the
synthesised audio: how near it is to the canonical recording, how
steady it is between utterances, and how near it comes to any real
person.

The scale is not universal and must be read from the cohort: different
people reach about 0.54 here, the same person about 0.86.
"""
import os, sys, glob, itertools
import numpy as np, soundfile as sf, sherpa_onnx

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL = os.path.join(HERE, "campplus.onnx")
if not os.path.isfile(MODEL):
    print("нет campplus.onnx рядом со свёртком — скачайте:")
    print("  https://huggingface.co/csukuangfj/speaker-embedding-models/"
          "resolve/main/3dspeaker_speech_campplus_sv_zh_en_16k-common_advanced.onnx")
    raise SystemExit(1)

ex = sherpa_onnx.SpeakerEmbeddingExtractor(
    sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=MODEL, num_threads=4))


def embed(path):
    wav, rate = sf.read(path, dtype="float32")
    if wav.ndim > 1:
        wav = wav.mean(axis=1)
    s = ex.create_stream()
    s.accept_waveform(rate, wav)
    s.input_finished()
    return np.array(ex.compute(s), dtype=np.float32)


def cos(a, b):
    return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b)))


made = sorted(glob.glob(os.path.join(sys.argv[1], "*.wav")))
if not made:
    print("нечего мерить в", sys.argv[1]); raise SystemExit(1)
canon = embed(os.path.join(HERE, "rina-voice-v1.wav"))
mine = [embed(p) for p in made]
pairs = [cos(a, b) for a, b in itertools.combinations(mine, 2)]
print("записей: %d" % len(mine))
print("до канонического голоса: %.3f" % np.mean([cos(v, canon) for v in mine]))
print("между собой:             %.3f" % (np.mean(pairs) if pairs else float("nan")))
print()
print("ориентиры этой шкалы: разные люди до ~0.54, тот же человек ~0.86")
