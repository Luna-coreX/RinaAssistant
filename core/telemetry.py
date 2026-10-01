# -*- coding: utf-8 -*-
"""
Telemetry for the beta, and only for the beta (`4.0b-D05`, `4.0-S04`).

The beta is there to learn what people use and where they give up, and
telemetry is the one way to learn it from people who do not write in. So it
exists here — off until a person switches it on, and gone in 4.0.0 Stable,
where `4.0-S04` takes it out and the promise «no telemetry» comes back.

**What leaves is counted, never said.** Every field is a number or a word
from a closed vocabulary known in advance: the names of intents from
`core.intent.INTENTS`, the names of built-in tools, their error codes and
the one-word reasons they give, the engines chosen from the settings'
own choices, the version of the program and of Windows. Anything outside
the vocabulary becomes `other`; a plugin's tool becomes `plugin`, because
the name of what a person installed is theirs. There is no field for text,
and so no way for a phrase, a path, a name or an address to get into one.

**Off means nothing.** Nothing is counted while it is off, nothing is kept,
and nothing is sent: `tools/test_telemetry.py` drives the core with the
network made to explode and holds that no connection is opened. Switching
it off deletes what was gathered and the installation's random identifier,
so switching it on again starts somebody new rather than resuming them.

**What left is shown.** Every report sent is kept beside the settings, and
the privacy page shows it: a person who switched this on can read exactly
what the server received, in the form it received it.
"""
import io
import json
import os
import platform
import re
import secrets
import threading
import time

#: Where reports go: the collector in `server/telemetry/`, on Vercel. Left
#: empty, nothing is sent, and the privacy page says so rather than letting
#: a person believe otherwise.
ENDPOINT = "https://rina-telemetry.vercel.app/api/v1/report"

#: The shape of a report. The collector refuses any other.
SCHEMA = 1

#: How often at most a report goes out.
EVERY = 24 * 3600

#: How many sent reports are kept for the privacy page.
KEEP_SENT = 30

#: How many readings of each timing are kept between reports.
KEEP_TIMINGS = 200

#: The timings measured, by name.
TIMINGS = ("recognition", "first_sound")

#: A word allowed into a report: a built-in identifier, nothing else.
WORD = re.compile(r"^[a-z][a-z0-9_.]{0,47}$")

FILE = "telemetry.json"
SENT_FILE = "telemetry-sent.jsonl"


def _allowed(word, known=None):
    """A word from the vocabulary, or `other`."""
    word = str(word or "")
    if known is not None:
        return word if word in known else "other"
    return word if WORD.match(word) else "other"


def _post(url, report, timeout=10.0):
    """Send one report. True if the server took it."""
    import urllib.request

    body = json.dumps(report, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as answer:
            return 200 <= answer.status < 300
    except Exception:                                   # noqa: BLE001
        return False


class Telemetry:
    """Counts, keeps and sends — while, and only while, it is switched on."""

    def __init__(self, settings, folder=None, clock=time.time, post=None,
                 endpoint=None):
        self._settings = settings
        self._folder = folder
        self._clock = clock
        self._post = post or _post
        self._endpoint = ENDPOINT if endpoint is None else endpoint
        self._lock = threading.RLock()
        self._state = None
        self._dirty = False

    # -- where it lives -------------------------------------------------------
    def _path(self, name):
        folder = self._folder
        if folder is None:
            from core.settings_store import config_dir

            folder = config_dir()
        return os.path.join(folder, name)

    @property
    def enabled(self):
        try:
            return bool(self._settings.get("telemetry", False))
        except Exception:                               # noqa: BLE001
            return False

    def _load(self):
        if self._state is not None:
            return self._state
        try:
            with io.open(self._path(FILE), encoding="utf-8") as f:
                self._state = json.load(f)
        except (OSError, ValueError):
            self._state = None
        if not isinstance(self._state, dict) or not self._state.get("install"):
            self._state = {
                # Random, made when counting starts and gone when it stops:
                # it lets the server tell one person's days apart from
                # another's, and it is tied to nothing else.
                "install": secrets.token_hex(16),
                "since": self._clock(),
                "features": {}, "tools": {}, "errors": {}, "reasons": {},
                "timings": {name: [] for name in TIMINGS},
            }
            self._dirty = True
        return self._state

    def _save(self):
        if not self._dirty or self._state is None:
            return
        path = self._path(FILE)
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            spare = path + ".tmp"
            with io.open(spare, "w", encoding="utf-8") as f:
                json.dump(self._state, f, ensure_ascii=False)
            os.replace(spare, path)
            self._dirty = False
        except OSError:
            pass

    def _add(self, group, word):
        state = self._load()
        counts = state.setdefault(group, {})
        counts[word] = int(counts.get(word, 0)) + 1
        self._dirty = True

    # -- what is counted ------------------------------------------------------
    def intent(self, name):
        """A command was understood as this."""
        if not self.enabled:
            return
        from core.intent import INTENTS

        with self._lock:
            self._add("features", _allowed(name, INTENTS))

    def tool(self, name, ok, error_code="", reason=""):
        """A tool was called. A plugin's is counted as `plugin`, unnamed."""
        if not self.enabled:
            return
        from core.toolbox import ALL_TOOLS

        name = str(name or "")
        own = not name.startswith("plugin.")
        # A name of the registry's or `other` — checked against the list,
        # as intents are, not against the shape of a word. Until
        # `4.0b-K01` only the program's own code named tools, and the
        # shape was enough; a person's command card names one too now, and
        # a Latin word typed into it would have left the machine as it was.
        word = (_allowed(name, {t.name for t in ALL_TOOLS}) if own
                else "plugin")
        with self._lock:
            self._add("tools", word)
            if not ok:
                code = _allowed(error_code) if own else "plugin"
                self._add("errors", f"{word}:{code}")
            if own and reason:
                self._add("reasons", f"{word}:{_allowed(reason)}")

    def timing(self, what, seconds):
        """How long a part of the pipeline took."""
        if not self.enabled or what not in TIMINGS:
            return
        with self._lock:
            readings = self._load()["timings"].setdefault(what, [])
            readings.append(round(float(seconds), 3))
            del readings[:-KEEP_TIMINGS]
            self._dirty = True

    # -- what goes out --------------------------------------------------------
    def report(self):
        """The report as it would be sent now, or None while it is off."""
        if not self.enabled:
            return None
        with self._lock:
            state = self._load()
            timings = {}
            for what in TIMINGS:
                readings = sorted(state.get("timings", {}).get(what, []))
                if readings:
                    last = len(readings) - 1
                    timings[what] = {
                        "n": len(readings),
                        "p50_ms": int(readings[last // 2] * 1000),
                        "p90_ms": int(readings[int(last * 0.9)] * 1000),
                    }
            days = max(1, int((self._clock() - state.get("since", self._clock()))
                              // 86400) + 1)
            return {
                "schema": SCHEMA,
                "install": state["install"],
                "app": _version(),
                "os": _windows(),
                "language": "ru" if str(self._settings.get("ui_language", ""))
                            .startswith("Рус") else "en",
                "days": days,
                "engines": self._engines(),
                "features": dict(state.get("features", {})),
                "tools": dict(state.get("tools", {})),
                "errors": dict(state.get("errors", {})),
                "reasons": dict(state.get("reasons", {})),
                "timings": timings,
            }

    def _engines(self):
        """Which engines are chosen — as the settings' own choices, nothing else."""
        from core.settings_schema import options_for

        out = {}
        for key in ("stt_engine", "tts_engine"):
            value = str(self._settings.get(key, "") or "")
            try:
                known = {o["value"] for o in options_for(key, self._settings)}
            except Exception:                           # noqa: BLE001
                known = set()
            out[key] = value if value in known else "other"
        out["model"] = bool(self._settings.get("llm_enabled", False))
        out["always_listen"] = bool(self._settings.get("always_listen", False))
        out["personality"] = ("own" if self._settings.get("personality")
                              == "own" else "rina")
        return out

    def due(self):
        with self._lock:
            state = self._load()
            return self._clock() - state.get("sent_at", state.get("since", 0)) \
                >= EVERY

    def maybe_send(self, force=False):
        """
        Send what was gathered, if it is time. Returns what happened.

        `off` — switched off, nothing touched; `no_endpoint` — nowhere to
        send yet; `insecure` — the address is not `https://`, so nothing
        is sent; `not_due` — too soon; `sent` — the server took it;
        `failed` — it did not, and the counts wait for the next try.
        """
        if not self.enabled:
            return "off"
        with self._lock:
            self._save()
            if not self._endpoint:
                return "no_endpoint"
            # Over TLS or not at all. A report holds nothing a person said,
            # but it does hold an identifier and a day's habits, and an
            # `http://` typed into `ENDPOINT` by mistake would have sent
            # them in the clear without a word.
            if not self._endpoint.lower().startswith("https://"):
                return "insecure"
            if not force and not self.due():
                return "not_due"
            report = self.report()
        if not self._post(self._endpoint, report):
            return "failed"
        with self._lock:
            self._keep_sent(report)
            # What was sent is not counted twice: the counts start again,
            # the identifier stays.
            state = self._load()
            for group in ("features", "tools", "errors", "reasons"):
                state[group] = {}
            state["timings"] = {name: [] for name in TIMINGS}
            state["since"] = state["sent_at"] = self._clock()
            self._dirty = True
            self._save()
        return "sent"

    def _keep_sent(self, report):
        path = self._path(SENT_FILE)
        try:
            lines = []
            if os.path.exists(path):
                with io.open(path, encoding="utf-8") as f:
                    lines = [line for line in f.read().splitlines() if line]
            lines.append(json.dumps({"at": self._clock(), "report": report},
                                    ensure_ascii=False))
            with io.open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines[-KEEP_SENT:]) + "\n")
        except OSError:
            pass

    def sent(self):
        """The reports that left, newest last: what the privacy page shows."""
        try:
            with io.open(self._path(SENT_FILE), encoding="utf-8") as f:
                return [json.loads(line) for line in f.read().splitlines()
                        if line.strip()]
        except (OSError, ValueError):
            return []

    def forget(self):
        """
        Switched off: drop what was gathered and the identifier.

        The record of what was sent stays — it is the person's evidence of
        what left, and the privacy page's «erase» is where it goes.
        """
        with self._lock:
            self._state = None
            self._dirty = False
            try:
                os.remove(self._path(FILE))
            except OSError:
                pass

    def flush(self):
        """Write the counts down — at shutdown and before a report."""
        with self._lock:
            self._save()


def _version():
    try:
        from version import APP_VERSION

        return str(APP_VERSION)
    except Exception:                                   # noqa: BLE001
        return "other"


def _windows():
    """The version of Windows as numbers — `10.0.26200` — and nothing else."""
    found = re.match(r"^\d+(\.\d+){0,3}$", platform.version() or "")
    return f"windows {found.group(0)}" if found else "other"
