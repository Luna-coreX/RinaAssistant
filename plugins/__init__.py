"""
The plugin API, its manager and the plugins that ship.

A plugin may import a module of its own as `plugins.<id>.<module>` — the
"Пересчёт" example does, and so does the weather plugin. That resolves
while the plugin sits in this folder. When the plugins live elsewhere —
`RINA_PLUGINS_DIR`, which the checks set (`tools/sandbox.py`) — that
folder is searched as well, or the plugin loads in the program and fails
in the checks: «No module named 'plugins.convert'» (found 2026-10-01).
"""
import os

_elsewhere = os.environ.get("RINA_PLUGINS_DIR")
if _elsewhere and os.path.isdir(_elsewhere) and _elsewhere not in __path__:
    __path__.append(_elsewhere)
