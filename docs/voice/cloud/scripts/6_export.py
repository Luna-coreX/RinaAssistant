# -*- coding: utf-8 -*-
"""Step 6. Piper's own export, with the exporter it was written for.

torch 2.14 exports through `torch.export` (dynamo) by default; Piper passes
`dynamic_axes`, which only the TorchScript exporter honours, and dynamo
falls over on the VITS flow. Forcing `dynamo=False` from outside leaves the
installed package as it is.

To run — the arguments of `piper.train.export_onnx`:

    python scripts/6_export.py --checkpoint last.ckpt --output-file rina.onnx
"""
import runpy
import sys

import torch

_export = torch.onnx.export


def export(*args, **kwargs):
    kwargs.setdefault("dynamo", False)
    return _export(*args, **kwargs)


torch.onnx.export = export
sys.argv = ["export_onnx"] + sys.argv[1:]
runpy.run_module("piper.train.export_onnx", run_name="__main__")
