# -*- coding: utf-8 -*-
"""
Downloadable models: the catalogue, and fetching them with progress.

Plan item `4.0b-A14`. Recognition and speech need files that cannot go into
an installer — the small Russian Vosk model is forty-six megabytes and the
full one is nearly two gigabytes. In 3.1.0 a person met this at the setup
wizard; the port lost the wizard, and with it the only place where anybody
was ever told that a model was needed at all.

**The catalogue is here rather than in the shell.** Which model an engine
needs is knowledge about engines, and engines are the core's (ADR 0006).
The shell shows a list and a progress bar; it does not know what Vosk is.

**Two kinds of entry, and the difference is stated rather than hidden.**
Some models we fetch ourselves — a plain archive at a known address, so the
progress is real bytes and cancelling actually stops a transfer. Others the
engine fetches on first use, and for those the honest thing to show is
"about this much, on first use", not a progress bar we would have to invent.
Pretending we control a transfer we do not is how a cancel button comes to
do nothing.

There is no Qt here: the module lies in the core.
"""

import os
import threading
import urllib.request
import zipfile

from core.logging_setup import get_logger
from core.settings_store import config_dir


log = get_logger("models")


class Model:
    """One downloadable thing and what it is for."""

    __slots__ = ("id", "title", "url", "size", "engine", "setting", "note",
                 "wanted")

    def __init__(self, id, title, engine, size, url="", setting="", note="",
                 wanted=False):
        self.id = id
        self.title = title
        #: Which engine setting this model belongs to (`stt_engine` value).
        self.engine = engine
        #: Bytes. Real, and checked against the server when we fetch.
        self.size = size
        #: Empty means the engine fetches it itself on first use.
        self.url = url
        #: The settings key that must point at the unpacked model, if any.
        self.setting = setting
        self.note = note
        #: Ticked by default in the setup wizard.
        #:
        #: Only the small one. The full Russian Vosk is nearly two
        #: gigabytes, and a box ticked in advance is a box a person does not
        #: read: they would agree to that download by not noticing it. What
        #: is offered ready-ticked has to be something nobody minds having
        #: agreed to.
        self.wanted = wanted

    @property
    def ours(self) -> bool:
        """Do we fetch this one, or does the engine."""
        return bool(self.url)


#: What can be had, and what it costs.
#:
#: Sizes are the ones the servers report, checked rather than remembered:
#: a number in a wizard is a promise about somebody's traffic.
CATALOGUE = (
    Model("vosk-ru-small", "Vosk: русский, малый", "vosk",
          size=46 * 1024 * 1024,
          url="https://alphacephei.com/vosk/models/"
              "vosk-model-small-ru-0.22.zip",
          setting="vosk_model",
          wanted=True,
          note="Быстрый и нетребовательный. Хватает для команд."),
    Model("vosk-ru-full", "Vosk: русский, полный", "vosk",
          size=1938 * 1024 * 1024,
          url="https://alphacephei.com/vosk/models/vosk-model-ru-0.42.zip",
          setting="vosk_model",
          note="Точнее, но почти два гигабайта и заметно больше памяти."),
    Model("whisper-base", "Whisper: base", "whisper",
          size=145 * 1024 * 1024,
          note="Скачается сам при первом распознавании."),
)


def models_dir() -> str:
    """Where unpacked models live."""
    path = os.path.join(config_dir(), "models")
    os.makedirs(path, exist_ok=True)
    return path


def installed(model: Model) -> str:
    """The path to this model on disk, or an empty string."""
    if not model.ours:
        return ""
    where = os.path.join(models_dir(), model.id)
    return where if os.path.isdir(where) else ""


def catalogue(settings=None) -> list[dict]:
    """The catalogue as the shell sees it."""
    return [
        {
            "id": m.id,
            "title": m.title,
            "engine": m.engine,
            "size": m.size,
            "note": m.note,
            "ours": m.ours,
            "wanted": m.wanted,
            "installed": bool(installed(m)) if m.ours else False,
        }
        for m in CATALOGUE
    ]


def find(model_id: str):
    for model in CATALOGUE:
        if model.id == model_id:
            return model
    return None


class Fetch:
    """
    One download, running in its own thread, that can be stopped.

    Cancelling is checked between blocks rather than by killing the thread:
    a half-written file left behind by a killed thread looks exactly like a
    finished one, and the next start would load it and fail somewhere far
    away from here.
    """

    #: Big enough not to spend the whole time in Python, small enough that
    #: "stop" is answered within a moment.
    BLOCK = 256 * 1024

    def __init__(self, model: Model, on_progress=None, settings=None):
        self.model = model
        self.on_progress = on_progress
        self.settings = settings
        self.done = 0
        self.total = model.size
        self.error = ""
        self._stop = threading.Event()
        self._thread = None

    def start(self) -> "Fetch":
        self._thread = threading.Thread(target=self._run, daemon=True,
                                        name=f"rina-fetch-{self.model.id}")
        self._thread.start()
        return self

    def cancel(self) -> None:
        self._stop.set()

    @property
    def cancelled(self) -> bool:
        return self._stop.is_set()

    def _say(self, state: str) -> None:
        if self.on_progress is None:
            return
        self.on_progress({
            "id": self.model.id,
            "state": state,
            "done": self.done,
            "total": self.total,
            "error": self.error,
        })

    def _run(self) -> None:
        archive = os.path.join(models_dir(), self.model.id + ".part")
        target = os.path.join(models_dir(), self.model.id)
        try:
            self._say("downloading")
            with urllib.request.urlopen(self.model.url, timeout=60) as answer:
                told = int(answer.headers.get("Content-Length") or 0)
                if told:
                    # What the server says beats what the catalogue
                    # remembers: a model gets rebuilt, and a progress bar
                    # that runs past its end is worse than none.
                    self.total = told
                with open(archive, "wb") as file:
                    while not self._stop.is_set():
                        block = answer.read(self.BLOCK)
                        if not block:
                            break
                        file.write(block)
                        self.done += len(block)
                        self._say("downloading")

            if self._stop.is_set():
                self._tidy(archive)
                self._say("cancelled")
                return

            self._say("unpacking")
            with zipfile.ZipFile(archive) as zipped:
                zipped.extractall(target)
            self._tidy(archive)

            # The archives carry one folder inside; the engine wants that
            # folder, not its parent.
            inner = [os.path.join(target, name) for name in os.listdir(target)]
            if len(inner) == 1 and os.path.isdir(inner[0]):
                where = inner[0]
            else:
                where = target

            if self.model.setting and self.settings is not None:
                self.settings.set(self.model.setting, where)
                self.settings.save()

            log.info("Модель %s готова: %s", self.model.id, where)
            self._say("ready")
        except Exception as exc:                        # noqa: BLE001
            self.error = str(exc)
            self._tidy(archive)
            log.warning("Модель %s не скачалась: %s", self.model.id, exc)
            self._say("failed")

    @staticmethod
    def _tidy(path: str) -> None:
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError:
            pass
