# -*- coding: utf-8 -*-
"""Step 5. Continue training from a generator alone.

The first cloud run's checkpoint came back damaged: 236 of its 3152 records,
in one run — the optimizers' states, the callbacks' state and four tensors
of the discriminator. The generator, which is the voice, was whole and was
taken out (`rina-epoch4696-generator-only.ckpt`, the discriminator of epoch
4396 beside it). Without the optimizers' states `--ckpt_path` cannot go on
from it, and Piper has no way to start from weights alone.

This is the ordinary `piper.train fit` with one callback added. It loads the
weights before the first step and rebuilds what was lost, in two phases:

- **rebuild** — the generator's rate is 0: its weights do not move, and the
  optimizer's moments fill from real gradients. The discriminator's rate
  rises meanwhile, and it catches up with a generator 300 epochs newer than
  itself. A fresh AdamW takes nearly full-size steps on every weight at
  first; taken by the generator, that is a jolt that could knock the voice.
- **warm-up** — the generator's rate rises to `RATE`, and training goes on.

The first checkpoint the run saves is whole again, and continues with
`--ckpt_path` like any other.

To run — the arguments of `piper.train fit`, without `--ckpt_path`:

    python scripts/5_continue.py rina-epoch4696-generator-only.ckpt \\
        --data.csv_path ... --trainer.max_epochs 300 ...

Epochs count from 0 again: `--trainer.max_epochs` is how many more, not up
to which. `--rebuild N` and `--warmup N`, given first, change the phases.
"""
import sys

import lightning as L
import torch
from piper.train.__main__ import _DEFAULT_CALLBACKS, VitsLightningCLI
from piper.train.vits.dataset import VitsDataModule
from piper.train.vits.lightning import VitsModel

#: The rate both optimizers carried through both fine-tunes, read from the
#: whole checkpoint of epoch 4396. Not the hyperparameters' 2e-4 and 1e-4:
#: the scheduler stopped at epoch 4140 with the base model, the current
#: Piper never steps it (it optimizes by hand, and nothing calls the
#: scheduler), and `--ckpt_path` restored this saved rate over the
#: configured one. Going on at another rate would change the conditions
#: the voice was trained under.
RATE = 1.1919788606289465e-4

#: Steps of each phase. At batch 32 on 700 phrases an epoch is about 19
#: steps: ten epochs a phase, well under a minute each on a 4090.
REBUILD = 200
WARMUP = 200


class ContinueFromGenerator(L.Callback):
    """Load the weights, then bring the rates up without jolting the voice."""

    def __init__(self, path, rebuild=REBUILD, warmup=WARMUP):
        self.path = path
        self.rebuild = rebuild
        self.warmup = warmup
        self.step = 0

    def on_fit_start(self, trainer, module):
        checkpoint = torch.load(self.path, map_location="cpu", weights_only=True)
        module.load_state_dict(checkpoint["state_dict"])
        print(f"веса: {self.path}, эпоха {checkpoint.get('epoch')}; "
              f"восстановление {self.rebuild} шагов, разогрев {self.warmup}, "
              f"скорость {RATE:.3e}", flush=True)

    def _rates(self, trainer, g, d):
        opt_g, opt_d = trainer.optimizers
        for group in opt_g.param_groups:
            group["lr"] = g
        for group in opt_d.param_groups:
            group["lr"] = d

    def on_train_batch_start(self, trainer, module, batch, batch_idx):
        if self.step > self.rebuild + self.warmup:
            return                      # set once below, left alone after
        d = RATE * min(1.0, (self.step + 1) / max(1, self.rebuild))
        if self.step < self.rebuild:
            g = 0.0
        else:
            g = RATE * min(1.0, (self.step - self.rebuild + 1) / max(1, self.warmup))
        self._rates(trainer, g, d)
        self.step += 1


def main():
    args = sys.argv[1:]
    if not args or args[0].startswith("--") and args[0] not in ("--rebuild", "--warmup"):
        print(__doc__)
        return 2
    phases = {"--rebuild": REBUILD, "--warmup": WARMUP}
    while args and args[0] in phases:
        phases[args[0]] = int(args[1])
        args = args[2:]
    path, rest = args[0], args[1:]
    if any(a.startswith("--ckpt_path") for a in rest):
        print("без --ckpt_path: веса берутся из генератора, первым аргументом")
        return 2

    sys.argv = [sys.argv[0], "fit", *rest]
    VitsLightningCLI(
        VitsModel, VitsDataModule,
        trainer_defaults={
            "max_epochs": -1,
            "callbacks": _DEFAULT_CALLBACKS + [ContinueFromGenerator(
                path, rebuild=phases["--rebuild"], warmup=phases["--warmup"])],
        },
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
