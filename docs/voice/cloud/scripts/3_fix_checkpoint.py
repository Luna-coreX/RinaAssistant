# -*- coding: utf-8 -*-
"""Step 3. Make a Piper checkpoint loadable where it was not made.

Two things stop a released checkpoint from loading. It carries
`pathlib.PosixPath` objects, which torch 2.6 and later refuse by
default and which Windows cannot even construct; and it carries the
trainer settings of the version it was made with, sixty of which the
current model has no name for, so the command line refuses to start.

Both are stripped once, here. Run this on the base checkpoint from
`rhasspy/piper-checkpoints` before training; skip it when resuming from
a checkpoint this bundle made.
"""
import os, sys, inspect, pathlib
import torch
from piper.train.vits.lightning import VitsModel

src = sys.argv[1]
dst = sys.argv[2] if len(sys.argv) > 2 else src.replace(".ckpt", "-portable.ckpt")

was = pathlib.PosixPath
pathlib.PosixPath = pathlib.PurePosixPath
try:
    ckpt = torch.load(src, map_location="cpu", weights_only=False)
finally:
    pathlib.PosixPath = was


def plain(value, depth=0):
    if isinstance(value, pathlib.PurePath):
        return str(value)
    if isinstance(value, dict):
        return {k: plain(v, depth + 1) for k, v in value.items()}
    if isinstance(value, (list, tuple)) and depth < 6:
        return type(value)(plain(v, depth + 1) for v in value)
    return value


for key in list(ckpt):
    if key != "state_dict":
        ckpt[key] = plain(ckpt[key])

accepted = set(inspect.signature(VitsModel.__init__).parameters) - {"self"}
hp = ckpt.get("hyper_parameters", {})
extra = [k for k in hp if k not in accepted]
for k in extra:
    hp.pop(k)
ckpt["hyper_parameters"] = hp

torch.save(ckpt, dst)
print("убрано лишних гиперпараметров: %d" % len(extra))
print("записано:", dst)
torch.load(dst, map_location="cpu", weights_only=True)
print("проверено: загружается при weights_only=True")
