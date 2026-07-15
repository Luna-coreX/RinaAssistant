"""
История взаимодействий: распознанные фразы, введённые команды и ответы Рины.

Хранится в конфиге (settings["history"]) как список записей:
    {"ts": 1700000000.0, "kind": "user"|"assistant"|"system",
     "text": "...", "source": "voice"|"typed"|"..."}

Запись включается настройкой save_history. Ограничиваем размер, чтобы файл
не разрастался.
"""

import time

MAX_ENTRIES = 300


class HistoryStore:
    def __init__(self, settings):
        self._settings = settings

    def enabled(self):
        return bool(self._settings.get("save_history", True))

    def all(self):
        return list(self._settings.get("history", []) or [])

    def add(self, kind, text, source=""):
        if not self.enabled():
            return
        text = str(text).strip()
        if not text:
            return
        entries = self.all()
        entries.append({
            "ts": time.time(),
            "kind": kind,
            "text": text,
            "source": source,
        })
        # обрезаем до последних MAX_ENTRIES
        if len(entries) > MAX_ENTRIES:
            entries = entries[-MAX_ENTRIES:]
        self._settings.set("history", entries)
        self._settings.save()

    def clear(self):
        self._settings.set("history", [])
        self._settings.save()
