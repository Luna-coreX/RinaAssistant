"""
The journal of tool calls.

Plan item 4.0-C06. Every call: the time, the tool, the arguments, the
initiator, the permissions, the result. Later this is the only way to
understand what Rina got up to — and the only source for the "Why?" feature
from 4.0b-B04.

**Refusals are recorded on a par with successes.** An attempt to shut the
computer down without confirmation is the most interesting entry in the
journal, and it must not be lost.

## Privacy

The arguments contain what a person said: a search query, a question to the
model, a reminder's text. Recording them verbatim means keeping a transcript
of conversations in a database — precisely what the product promises not to
do.

The rule was derived from a tool's schema rather than from a list of
exceptions: **an argument has a list of permissible values — so it is not a
person's text but a choice from a known set, and it is written verbatim.**
`power_action {"action": "shutdown"}` is recorded whole, because "shutdown"
came from a list. Whereas `web_search {"query": ...}` is free text, and only
its length remains.

That way the journal answers the question "what did she do" without
answering the question "what was she asked about". Verbatim recording is
switched on by the same `log_texts` setting as in the application's journal:
one decision, one place.

## Why a database and not a file

The journal is needed with selection: the last calls, one tool's calls,
refusals only, the dangerous only. Over a text file that is done by parsing
lines, which will one day lie. SQLite is part of the standard library; there
are no new dependencies.

There is no Qt here: the module lies in the core.
"""

import json
import os
import sqlite3
import threading
import time

from core.logging_setup import get_logger


log = get_logger("audit")

FILE_NAME = "audit.db"

#: How long to keep it. The journal is there to look into the recent past,
#: not to keep a chronicle: without a limit it grows until it becomes a
#: problem in itself.
KEEP_DAYS = 30
KEEP_ROWS = 50_000

SCHEMA = """
CREATE TABLE IF NOT EXISTS calls (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ts              REAL    NOT NULL,
    tool            TEXT    NOT NULL,
    args            TEXT    NOT NULL,
    source          TEXT    NOT NULL,
    permissions     TEXT    NOT NULL,
    ok              INTEGER NOT NULL,
    error_code      TEXT    NOT NULL DEFAULT '',
    duration_ms     INTEGER NOT NULL DEFAULT 0,
    confirmation_id TEXT    NOT NULL DEFAULT '',
    trace_id        TEXT    NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_calls_ts   ON calls(ts);
CREATE INDEX IF NOT EXISTS idx_calls_tool ON calls(tool);
CREATE INDEX IF NOT EXISTS idx_calls_ok   ON calls(ok);
"""


def redact_args(tool, args, verbatim=False):
    """
    The arguments in a form fit for the journal.

    What came from a list of permissible values, numbers and booleans are
    written verbatim. Free text is replaced by its length.
    """
    out = {}
    for key, value in (args or {}).items():
        param = tool.param(key) if tool is not None else None

        if verbatim or isinstance(value, (int, float, bool)):
            out[key] = value
            continue
        if param is not None and param.choices:
            out[key] = value
            continue
        if isinstance(value, str):
            out[key] = f"<{len(value)} симв.>"
        elif isinstance(value, (list, tuple)):
            out[key] = f"<{len(value)} эл.>"
        elif value is None:
            out[key] = None
        else:
            out[key] = f"<{type(value).__name__}>"
    return out


class AuditLog:
    """The journal of calls. Appending and reading only."""

    def __init__(self, path=None, keep_days=KEEP_DAYS, keep_rows=KEEP_ROWS):
        self._path = path or self._default_path()
        self._keep_days = keep_days
        self._keep_rows = keep_rows
        self._lock = threading.RLock()
        self._db = None
        self._writes = 0
        self._open()

    @staticmethod
    def _default_path():
        from core.settings_store import config_dir

        return os.path.join(config_dir(), FILE_NAME)

    def _open(self):
        try:
            if self._path != ":memory:":
                os.makedirs(os.path.dirname(self._path), exist_ok=True)
            # The connection outlives threads: writing comes both from the
            # command thread and from the reminder scheduler. Consistency is
            # held by the lock.
            self._db = sqlite3.connect(self._path, check_same_thread=False)
            self._db.executescript(SCHEMA)
            self._db.commit()
        except sqlite3.Error:
            # The application works without a journal; it must not fall over because of one.
            log.exception("Не удалось открыть журнал вызовов: %s", self._path)
            self._db = None

    @property
    def path(self):
        return self._path

    @property
    def available(self):
        return self._db is not None

    # ------------------------------------------------------------------
    def record(self, *, tool, args, source, permissions, ok, error_code="",
               duration_ms=0, confirmation_id="", trace_id="", verbatim=False):
        """Record one call. `tool` is a Tool object or its name."""
        if self._db is None:
            return None

        name = getattr(tool, "name", tool)
        clean = redact_args(tool if hasattr(tool, "param") else None,
                            args, verbatim)
        row = (time.time(), name,
               json.dumps(clean, ensure_ascii=False, default=str),
               source or "", json.dumps(sorted(permissions or []),
                                        ensure_ascii=False),
               1 if ok else 0, error_code or "", int(duration_ms),
               confirmation_id or "", trace_id or "")
        try:
            with self._lock:
                cursor = self._db.execute(
                    "INSERT INTO calls (ts, tool, args, source, permissions,"
                    " ok, error_code, duration_ms, confirmation_id, trace_id)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?)", row)
                self._db.commit()
                self._writes += 1
                if self._writes % 200 == 0:
                    self._prune_locked()
                return cursor.lastrowid
        except sqlite3.Error:
            log.exception("Не удалось записать вызов %s", name)
            return None

    # ------------------------------------------------------------------
    def recent(self, limit=50, tool=None, only_failures=False):
        """The last calls, newest first."""
        if self._db is None:
            return []
        query = ("SELECT id, ts, tool, args, source, permissions, ok,"
                 " error_code, duration_ms, confirmation_id, trace_id"
                 " FROM calls")
        where, params = [], []
        if tool:
            where.append("tool = ?")
            params.append(tool)
        if only_failures:
            where.append("ok = 0")
        if where:
            query += " WHERE " + " AND ".join(where)
        query += " ORDER BY id DESC LIMIT ?"
        params.append(int(limit))

        with self._lock:
            rows = self._db.execute(query, params).fetchall()
        return [self._to_dict(r) for r in rows]

    @staticmethod
    def _to_dict(row):
        return {
            "id": row[0], "ts": row[1], "tool": row[2],
            "args": json.loads(row[3]), "source": row[4],
            "permissions": json.loads(row[5]), "ok": bool(row[6]),
            "error_code": row[7], "duration_ms": row[8],
            "confirmation_id": row[9], "trace_id": row[10],
        }

    def count(self):
        if self._db is None:
            return 0
        with self._lock:
            return self._db.execute("SELECT COUNT(*) FROM calls").fetchone()[0]

    # ------------------------------------------------------------------
    def prune(self):
        with self._lock:
            return self._prune_locked()

    def _prune_locked(self):
        if self._db is None:
            return 0
        removed = 0
        try:
            cutoff = time.time() - self._keep_days * 86400
            removed += self._db.execute(
                "DELETE FROM calls WHERE ts < ?", (cutoff,)).rowcount
            removed += self._db.execute(
                "DELETE FROM calls WHERE id NOT IN ("
                " SELECT id FROM calls ORDER BY id DESC LIMIT ?)",
                (self._keep_rows,)).rowcount
            self._db.commit()
        except sqlite3.Error:
            log.exception("Не удалось подчистить журнал вызовов")
        return max(0, removed)

    def clear(self):
        """Erase the journal entirely — for "Forget this" from 4.0b-B02."""
        if self._db is None:
            return 0
        with self._lock:
            count = self.count()
            self._db.execute("DELETE FROM calls")
            self._db.commit()
            return count

    def close(self):
        with self._lock:
            if self._db is not None:
                self._db.close()
                self._db = None
