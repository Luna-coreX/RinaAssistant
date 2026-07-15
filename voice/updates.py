"""
Проверка обновлений.

Сравнивает текущую версию с последней, опубликованной на заданном endpoint.
По умолчанию endpoint пустой (нет своего сервера релизов) — тогда проверка
честно сообщает, что источник обновлений не настроен, вместо фальшивого «всё
актуально». Если указать URL (напр. GitHub Releases API), проверка заработает.

Сетевой запрос — в фоновом потоке, результат через сигнал Qt.
"""

import json
import threading
import urllib.request

from PySide6.QtCore import QObject, Signal

from core.i18n import t as tr
from version import APP_VERSION


# Укажите сюда URL, отдающий JSON с полем "tag_name" или "version",
# например GitHub: https://api.github.com/repos/<owner>/<repo>/releases/latest
UPDATE_ENDPOINT = ""


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
                tr("в ui/voice/updates.py, чтобы включить проверку."))
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
