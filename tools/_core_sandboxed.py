# -*- coding: utf-8 -*-
"""
Ядро под песочницей — только для проверок.

Отдельный запускатель, а не флаг внутри `rina_core.py`: выключатель побочных
эффектов, живущий в рабочем коде, однажды окажется включённым у пользователя,
и Рина перестанет что-либо делать, не сказав почему.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

from sandbox import neutralise
neutralise()

import rina_core
sys.exit(rina_core.main(sys.argv[1:]))
