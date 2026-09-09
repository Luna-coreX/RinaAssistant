# -*- coding: utf-8 -*-
"""
Fetching a recognition model, visibly and interruptibly.

Plan item `4.0-E05`. A Whisper model is a hundred and forty megabytes and a
Vosk one about forty-five: on a slow line that is minutes, and minutes with
nothing on the screen are indistinguishable from a program that has hung.

**Three promises, and each is here because its absence has a name.**

`1.` **It says how far it has got.** Not because a bar is pretty, but
because "downloading, 12 of 140 MB" and silence are different answers to
"is it working". The library would download this by itself on first use —
silently, inside the call that was supposed to recognise a phrase.

`2.` **It can be stopped.** A person who started a download on a metered
connection must be able to change their mind, and a cancel that only stops
the display is a lie. What is written to disk is thrown away with it: a
half a model left lying about is worse than none, because next time it will
be found and used.

`3.` **It is never started behind one's back.** Fetching is asked for, and
the asking is a separate step from choosing an engine. Picking "Whisper" in
a list is not consent to spend a hundred and forty megabytes of somebody
else's traffic.

There is no Qt here and no protocol: this module reports through a callback
and is told to stop through an event, so it can be checked without raising
either half of the application.
"""

import os
import shutil
import threading
import urllib.request

from core.logging_setup import get_logger


log = get_logger("models")

#: How much is read at a time. Small enough that cancelling feels instant,
#: large enough that the callback is not the expensive part.
CHUNK = 256 * 1024


class Cancelled(Exception):
    """The person changed their mind. Not a failure."""


class Progress:
    """How far a download has got. Plain data — it travels to the shell."""

    __slots__ = ("done", "total", "name")

    def __init__(self, name: str, done: int = 0, total: int = 0):
        self.name = name
        self.done = done
        self.total = total

    @property
    def share(self) -> float:
        """From zero to one; zero when the size is not known in advance."""
        return self.done / self.total if self.total > 0 else 0.0

    def to_dict(self) -> dict:
        return {"name": self.name, "done": self.done, "total": self.total,
                "share": round(self.share, 4)}


def fetch(url: str, into: str, name: str = "", on_progress=None,
          stop: threading.Event | None = None) -> str:
    """
    Download a file, telling how it goes and stopping when told.

    Returns the path it was written to. Raises `Cancelled` if it was
    stopped, and whatever the network raised otherwise — both leave nothing
    behind.
    """
    name = name or os.path.basename(url)
    os.makedirs(os.path.dirname(into) or ".", exist_ok=True)

    # Written beside the real name and moved into place at the end. A file
    # that appears only when it is whole cannot be found half-finished by
    # the next run — and being found half-finished is the one failure that
    # does not look like a failure.
    partial = into + ".part"
    progress = Progress(name)

    try:
        with urllib.request.urlopen(url, timeout=30) as answer:
            progress.total = int(answer.headers.get("Content-Length") or 0)
            if on_progress:
                on_progress(progress)

            with open(partial, "wb") as file:
                while True:
                    if stop is not None and stop.is_set():
                        raise Cancelled(name)
                    piece = answer.read(CHUNK)
                    if not piece:
                        break
                    file.write(piece)
                    progress.done += len(piece)
                    if on_progress:
                        on_progress(progress)
    except BaseException:
        # Including `Cancelled`, and deliberately: what was interrupted is
        # removed by whoever was writing it. Leaving that to the caller
        # means leaving it undone.
        if os.path.exists(partial):
            try:
                os.remove(partial)
            except OSError:
                log.warning("Не убрала недокачанное: %s", partial)
        raise

    os.replace(partial, into)
    log.info("Модель скачана: %s (%d Б)", name, progress.done)
    return into


def unpack(archive: str, into: str, stop: threading.Event | None = None) -> str:
    """
    Unpack a model archive next to itself, then throw the archive away.

    Vosk ships a zip; Whisper does not ship an archive at all. Unpacking is
    separate from fetching for that reason — an engine uses what it needs.
    """
    import zipfile

    os.makedirs(into, exist_ok=True)
    with zipfile.ZipFile(archive) as bundle:
        for entry in bundle.namelist():
            if stop is not None and stop.is_set():
                raise Cancelled(os.path.basename(archive))
            bundle.extract(entry, into)
    os.remove(archive)
    return into


def remove(path: str) -> bool:
    """Throw a model away. What was downloaded can be undownloaded."""
    if not os.path.exists(path):
        return False
    if os.path.isdir(path):
        shutil.rmtree(path, ignore_errors=True)
    else:
        os.remove(path)
    return True
