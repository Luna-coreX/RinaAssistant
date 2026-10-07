"""
The plugin API, its manager and the plugins that ship.

A plugin may import a module of its own as `plugins.<id>.<module>` — the
"Пересчёт" example does, and so does the weather plugin. That resolves
while the plugin sits in this folder. A person's plugins live elsewhere —
in the profile (`manager.plugins_dir`), or `RINA_PLUGINS_DIR`, which the
checks set (`tools/sandbox.py`) — and that folder is searched as well, or
the plugin loads in one place and fails in another: «No module named
'plugins.convert'» (found 2026-10-01). The profile's folder is added on
discovery (`manager.plugin_folders`), a plugin's process adds its own
(`host.py`).
"""
import os

_elsewhere = os.environ.get("RINA_PLUGINS_DIR")
if _elsewhere and os.path.isdir(_elsewhere) and _elsewhere not in __path__:
    __path__.append(_elsewhere)
