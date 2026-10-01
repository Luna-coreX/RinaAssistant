# -*- coding: utf-8 -*-
"""
The core under a sandbox — for the checks only.

A separate launcher rather than a flag inside `rina_core.py`: a switch for
side effects living in working code will one day turn out to be on at a
user's, and Rina will stop doing anything without saying why.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

from sandbox import isolate_plugins, neutralise
neutralise()
# The shell's checks open a plugin's own page, and since `4.0b-K05` the
# plugins with pages are examples, outside `plugins/`.
isolate_plugins()

import rina_core
sys.exit(rina_core.main(sys.argv[1:]))
