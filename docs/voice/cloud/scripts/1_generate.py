# -*- coding: utf-8 -*-
"""Step 1. VoxCPM2 speaks Rina's lines, on a card rather than a processor.

On the development machine this ran at an RTF near 19 — a day for an
hour of speech. On a CUDA card it is roughly 0.3, so the same corpus
takes half an hour. That difference is the whole reason this step is
here rather than at home.

Every line is spoken with the canonical recording as the prompt, so the
result is the same person throughout, and each line gets a seed of its
own so the run is repeatable.
"""
import os, sys, time
import soundfile as sf, torch
from voxcpm import VoxCPM

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROMPT = os.path.join(HERE, "rina-voice-v1.wav")
PROMPT_TEXT = "Привет. Я Рина, и это мой собственный голос."
OUT = os.path.join(HERE, "generated")
os.makedirs(OUT, exist_ok=True)

with open(os.path.join(HERE, "texts.txt"), encoding="utf-8") as f:
    lines = [x.strip() for x in f if x.strip()]
print("строк к озвучке:", len(lines))

model = VoxCPM.from_pretrained("openbmb/VoxCPM2", load_denoiser=False)
rate = model.tts_model.sample_rate
made = seconds = 0
started = time.perf_counter()
for at, text in enumerate(lines):
    path = os.path.join(OUT, "line_%04d.wav" % at)
    if os.path.isfile(path):
        continue
    torch.manual_seed(20260924 + at)
    try:
        wav = model.generate(text=text, prompt_wav_path=PROMPT,
                             prompt_text=PROMPT_TEXT, cfg_value=2.0,
                             inference_timesteps=10)
    except Exception as e:
        print("  %04d сбой: %s" % (at, e))
        continue
    sf.write(path, wav, rate)
    made += 1
    seconds += len(wav) / rate
    if made % 25 == 0:
        print("  %d строк, %.1f мин звука, прошло %.0f мин"
              % (made, seconds / 60, (time.perf_counter() - started) / 60),
              flush=True)

with open(os.path.join(HERE, "generated_texts.txt"), "w",
          encoding="utf-8", newline="\n") as f:
    f.write("\n".join(lines) + "\n")
print("готово: %d строк, %.1f минут" % (made, seconds / 60))
