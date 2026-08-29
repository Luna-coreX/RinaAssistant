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
        """
        Записи журнала, приведённые к ожидаемому виду.

        Файл истории могли отредактировать руками или повредить при сбое;
        одна испорченная запись не должна ломать всю вкладку, поэтому мусор
        отбрасывается здесь, а не в каждом месте показа.
        """
        clean = []
        for entry in (self._settings.get("history", []) or []):
            if not isinstance(entry, dict):
                continue
            try:
                stamp = float(entry.get("ts", 0) or 0)
            except (TypeError, ValueError):
                stamp = 0.0
            clean.append({
                "ts": stamp,
                "kind": str(entry.get("kind", "user")),
                "text": str(entry.get("text", "")),
                "source": str(entry.get("source", "")),
            })
        return clean

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
