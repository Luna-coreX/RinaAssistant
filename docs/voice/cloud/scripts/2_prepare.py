# -*- coding: utf-8 -*-
"""Step 2. The recordings, shaped for Piper without flattening them.

**One gain for the whole corpus, never one per clip.** Normalising each
recording to its own peak raised the loudness fivefold and squeezed the
difference between a quiet phrase and a loud one; the voice came out
pressed against the ceiling, denser and less airy than the original.
The crest factor showed it: 5.3 where the source had 7.9.

Silence is trimmed here rather than by the trainer, whose detector
changed its interface, and with a wide margin: the breath before a
phrase and the fall after it are part of how unhurried a voice sounds.
"""
import os, sys, glob
import numpy as np, soundfile as sf, torch, torchaudio

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(HERE, "generated")
OUT = os.path.join(HERE, "dataset")
WAV = os.path.join(OUT, "wav")
os.makedirs(WAV, exist_ok=True)
RATE = 22050
MARGIN = 0.12

with open(os.path.join(HERE, "generated_texts.txt"), encoding="utf-8") as f:
    lines = [x.strip() for x in f if x.strip()]

kept = []
for path in sorted(glob.glob(os.path.join(SRC, "line_*.wav"))):
    at = int(os.path.basename(path)[5:9])
    if at >= len(lines):
        continue
    wav, rate = sf.read(path, dtype="float32")
    if wav.ndim > 1:
        wav = wav.mean(axis=1)
    audio = torch.from_numpy(wav).unsqueeze(0)
    if rate != RATE:
        audio = torchaudio.transforms.Resample(rate, RATE)(audio)
    out = audio[0].numpy()
    peak = float(np.abs(out).max())
    loud = np.abs(out) > peak * 0.04
    if loud.any():
        pad = int(MARGIN * RATE)
        first = max(0, int(np.argmax(loud)) - pad)
        last = min(len(out), len(loud) - int(np.argmax(loud[::-1])) + pad)
        out = out[first:last]
    kept.append((os.path.basename(path)[:-4], lines[at], out))

top = max(float(np.abs(w).max()) for _, _, w in kept)
gain = 0.92 / top if top > 0 else 1.0

rows, total = [], 0.0
for name, text, w in kept:
    w = (w * gain).astype("float32")
    sf.write(os.path.join(WAV, name + ".wav"), w, RATE, subtype="PCM_16")
    rows.append((name + ".wav", text))
    total += len(w) / RATE

with open(os.path.join(OUT, "metadata.csv"), "w", encoding="utf-8",
          newline="\n") as f:
    for name, text in rows:
        f.write("%s|%s\n" % (name, text))

crest = []
for name, _ in rows:
    w, _ = sf.read(os.path.join(WAV, name), dtype="float32")
    r = float(np.sqrt(np.mean(w ** 2)))
    if r:
        crest.append(float(np.abs(w).max()) / r)
print("записей %d, %.1f минут, множитель %.2f" % (len(rows), total / 60, gain))
print("крест-фактор набора %.1f (у источника около 7.9 — держитесь ближе к нему)"
      % np.mean(crest))
