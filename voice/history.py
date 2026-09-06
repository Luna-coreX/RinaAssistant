"""
The history of interactions: recognised phrases, typed commands and Rina's
answers.

Kept in the config (settings["history"]) as a list of entries:
    {"ts": 1700000000.0, "kind": "user"|"assistant"|"system",
     "text": "...", "source": "voice"|"typed"|"..."}

Recording is switched on by the save_history setting. We limit the size, so
the file does not grow unchecked.
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
        The journal's entries, brought to the expected form.

        The history file may have been edited by hand or damaged in a
        failure; one spoiled entry must not break the whole tab, so the
        rubbish is discarded here rather than in every place that shows it.
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
        # reading, changing and writing as one indivisible operation:
        # otherwise a simultaneous answer and reminder overwrite each other's
        # entries
        with self._settings.transaction():
            entries = self.all()
            entries.append({
                "ts": time.time(),
                "kind": kind,
                "text": text,
                "source": source,
            })
            # we trim to the last MAX_ENTRIES
            if len(entries) > MAX_ENTRIES:
                entries = entries[-MAX_ENTRIES:]
            self._settings.set("history", entries)
            self._settings.save()

    def clear(self):
        self._settings.set("history", [])
        self._settings.save()
