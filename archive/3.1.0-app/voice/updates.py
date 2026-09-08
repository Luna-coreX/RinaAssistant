"""
Checking for updates.

Compares the current version with the latest one published at a given
endpoint. By default the endpoint is empty (there is no release server of
our own) — the check then honestly reports that no update source is set up,
instead of a false "everything is current". Setting a URL (the GitHub
Releases API, say) makes the check work.

The network request goes in a background thread, the result through a Qt
signal.
"""

import json
import threading
import urllib.request

from PySide6.QtCore import QObject, Signal

from core.i18n import t as tr
from version import APP_VERSION


# Put here a URL that gives out JSON with a "tag_name" or "version" field,
# for example GitHub:
# https://api.github.com/repos/<owner>/<repo>/releases/latest
UPDATE_ENDPOINT = "https://api.github.com/repos/Luna-corex/RinaAssistant/releases/latest"


def _parse_version(s):
    s = str(s).lstrip("vV").strip()
    parts = []
    for p in s.split("."):
        num = "".join(ch for ch in p if ch.isdigit())
        parts.append(int(num) if num else 0)
    return tuple(parts) if parts else (0,)


def _is_newer(remote, local):
    return _parse_version(remote) > _parse_version(local)


class UpdateChecker(QObject):
    checking = Signal()
    result = Signal(bool, str)   # (update_available, message)

    def check(self):
        self.checking.emit()
        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self):
        if not UPDATE_ENDPOINT:
            self.result.emit(
                False,
                tr("Источник обновлений не настроен. Укажите URL релизов ") +
                tr("в voice/updates.py, чтобы включить проверку."))
            return
        try:
            req = urllib.request.Request(
                UPDATE_ENDPOINT, headers={"User-Agent": "RinaAssistant"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            latest = data.get("tag_name") or data.get("version") or ""
            if not latest:
                self.result.emit(False, tr("Не удалось определить последнюю версию."))
                return
            if _is_newer(latest, APP_VERSION):
                self.result.emit(
                    True, f"Доступна новая версия {latest} "
                          f"(у вас {APP_VERSION}).")
            else:
                self.result.emit(
                    False, f"У вас последняя версия ({APP_VERSION}).")
        except Exception as e:
            self.result.emit(False, f"Не удалось проверить обновления: {e}")
