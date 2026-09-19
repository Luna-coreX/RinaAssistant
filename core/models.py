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
import shutil
import sys
import threading
import urllib.request
import zipfile

from core.logging_setup import get_logger
from core.settings_store import config_dir


log = get_logger("models")


class Model:
    """One downloadable thing and what it is for."""

    __slots__ = ("id", "title", "url", "files", "size", "engine", "setting",
                 "note", "wanted", "purpose")

    def __init__(self, id, title, engine, size, url="", setting="", note="",
                 wanted=False, purpose="stt", files=()):
        self.id = id
        self.title = title
        #: Hearing or speaking. Both are downloads and both were missing
        #: from a fresh machine; only one of them was ever offered. Kept as
        #: a field rather than guessed from the engine's name so that the
        #: wizard can say "to hear" and "to speak" instead of listing five
        #: things with no telling which is which.
        self.purpose = purpose
        #: Which engine setting this model belongs to (`stt_engine` or
        #: `tts_engine` value).
        self.engine = engine
        #: Bytes. Real, and checked against the server when we fetch.
        self.size = size
        #: Empty means the engine fetches it itself on first use.
        self.url = url
        #: Loose files instead of one archive, when that is what the model
        #: is. Piper's voice is an `.onnx` and the `.onnx.json` beside it,
        #: and packing them into a zip that does not exist was not an
        #: option. The setting is pointed at the first of them.
        self.files = tuple(files)
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
        return bool(self.url or self.files)


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

    # And a voice. There was none here at all, and that is how a fresh
    # machine turned out: `faster-whisper` comes with the runtime, so Rina
    # could hear out of the box and had no way whatever to answer aloud.
    # Neither the package nor the model for any speaking engine was
    # offered anywhere — found by a person installing on a second
    # computer.
    Model("piper-ru-irina", "Голос Piper: русский (Ирина)", "piper",
          # Measured against the server, not remembered: 63 201 294 for
          # the voice and 4 765 for the settings beside it.
          size=63_206_059,
          files=("https://huggingface.co/rhasspy/piper-voices/resolve/main/"
                 "ru/ru_RU/irina/medium/ru_RU-irina-medium.onnx",
                 "https://huggingface.co/rhasspy/piper-voices/resolve/main/"
                 "ru/ru_RU/irina/medium/ru_RU-irina-medium.onnx.json"),
          setting="piper_model",
          purpose="tts",
          note="Голос на этом компьютере, без интернета. "
               "Нужен пакет Piper."),
)


class Package:
    """A package the assistant can install for itself."""

    __slots__ = ("id", "title", "pip", "module", "engine", "size", "note",
                 "wanted", "purpose")

    def __init__(self, id, title, pip, module, engine, size, note="",
                 wanted=False, purpose="stt"):
        self.id = id
        self.title = title
        #: Hearing or speaking — see `Model.purpose`.
        self.purpose = purpose
        #: What to hand to `pip`. **Taken from here and nowhere else.**
        self.pip = pip
        #: What to import to find out whether it is already there.
        self.module = module
        self.engine = engine
        self.size = size
        self.note = note
        self.wanted = wanted


#: What may be installed. Closed, and in the code (`T-20`).
#:
#: **The name of a package is never taken from a message.** The shell names
#: an identifier; the name handed to `pip` is looked up here. Otherwise
#: "install this for me" would be "run this on my machine", and a typo in a
#: popular package's name is an ordinary way of spreading malicious code —
#: one a person cannot defend themselves against by choosing carefully,
#: because they do not know how it is spelled.
#:
#: The same rule as the tool registry and the closed list of reminder
#: occasions: everything that changes the world is named in advance.
PACKAGES = (
    Package("pkg-vosk", "Пакет Vosk", "vosk", "vosk", "vosk",
            size=14 * 1024 * 1024,
            wanted=True,
            note="Нужен, чтобы модель Vosk заработала."),
    Package("pkg-whisper", "Пакет Whisper", "faster-whisper",
            "faster_whisper", "whisper",
            size=60 * 1024 * 1024,
            note="Лёгкая сборка Whisper: те же модели, без torch."),

    # Speaking. Neither of these was here, and without them Rina has no
    # voice at all: the runtime carries `soundfile` and nothing that makes
    # sound to decode.
    Package("pkg-piper", "Пакет Piper", "piper-tts", "piper", "piper",
            # The wheel and `onnxruntime` under it.
            size=56 * 1024 * 1024,
            purpose="tts",
            note="Речь на этом компьютере. К нему нужен голос."),
    # Not ticked in advance, and the reason is not its size. It speaks by
    # sending the text to Microsoft, and a box ticked for somebody is a box
    # they do not read: they would agree to that by not noticing it. The
    # note says so where the choice is made.
    Package("pkg-edge", "Пакет Edge (онлайн)", "edge-tts", "edge_tts",
            "edge", size=4 * 1024 * 1024,
            purpose="tts",
            note="Голоса Microsoft. Текст реплики уходит к ним по сети; "
                 "модель скачивать не нужно."),
)


def have_package(package: Package) -> bool:
    """Is it already importable."""
    import importlib.util

    try:
        return importlib.util.find_spec(package.module) is not None
    except Exception:                                   # noqa: BLE001
        return False


def find_package(package_id: str):
    for package in PACKAGES:
        if package.id == package_id:
            return package
    return None


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


def catalogue(settings=None, running=None) -> list[dict]:
    """
    The catalogue as the shell sees it, including what is happening now.

    `running` maps a model's id to the download in flight for it. It is
    passed in rather than kept here: who is downloading what is the
    session's business, and a module-level register of it would be shared
    between two cores in one process — the very hidden global that `4.0-B05`
    was about.
    """
    # The catalogue is written as literals and translated here, on the
    # way out — the same boundary as the engine names in
    # `settings_schema.values()`: a table is keys, and the language is
    # chosen in settings. Without this the window showed «Пакет Vosk» in
    # Russian with «Downloaded.» under it in English, because the row's
    # chrome came from the shell's table and the row's name did not.
    from core.i18n import t as tr

    running = running or {}
    out = []
    for p in PACKAGES:
        item = {
            "id": p.id,
            "kind": "package",
            "title": tr(p.title),
            "purpose": p.purpose,
            "engine": p.engine,
            "size": p.size,
            "note": tr(p.note),
            "ours": True,
            "wanted": p.wanted,
            "installed": have_package(p),
        }
        live = running.get(p.id)
        if live is not None:
            item["state"] = live.state
            item["done"] = live.done
            item["total"] = live.total
            item["task_id"] = getattr(live, "task_id", "")
        out.append(item)

    for m in CATALOGUE:
        item = {
            "id": m.id,
            "kind": "model",
            "title": tr(m.title),
            "purpose": m.purpose,
            "engine": m.engine,
            "size": m.size,
            "note": tr(m.note),
            "ours": m.ours,
            "wanted": m.wanted,
            "installed": bool(installed(m)) if m.ours else False,
        }
        live = running.get(m.id)
        if live is not None:
            item["state"] = live.state
            item["done"] = live.done
            item["total"] = live.total
            item["task_id"] = getattr(live, "task_id", "")
        out.append(item)
    return out


def find(model_id: str):
    for model in CATALOGUE:
        if model.id == model_id:
            return model
    return None


class Install:
    """
    One package installation, in its own thread, that can be stopped.

    Reports like a download and is watched like one, so the window shows
    both the same way — but the numbers are different in kind. `pip` says
    what it is doing in lines, not in bytes, so there is no share to draw:
    `total` stays zero and the bar is left indeterminate. Inventing a
    percentage from the number of lines would be a bar that means nothing
    and moves convincingly.
    """

    def __init__(self, package: Package, on_progress=None, settings=None):
        self.package = package
        self.on_progress = on_progress
        self.settings = settings
        self.done = 0
        self.total = 0
        self.error = ""
        self.state = "waiting"
        self._stop = threading.Event()
        self._process = None
        self._thread = None

    def start(self) -> "Install":
        self._thread = threading.Thread(target=self._run, daemon=True,
                                        name=f"rina-pip-{self.package.id}")
        self._thread.start()
        return self

    def cancel(self) -> None:
        self._stop.set()
        process = self._process
        if process is not None and process.poll() is None:
            # Killed rather than asked: `pip` has no polite way to stop, and
            # a half-installed package is what an unclean stop leaves. The
            # importable check afterwards is what decides whether it counts
            # as installed, so a torn-off install reads as absent.
            try:
                process.kill()
            except Exception:                           # noqa: BLE001
                pass

    def _say(self, state: str, note: str = "") -> None:
        self.state = state
        if self.on_progress is None:
            return
        try:
            self.on_progress({
                "id": self.package.id,
                "state": state,
                "done": self.done,
                "total": self.total,
                "note": note,
                "error": self.error,
            })
        except Exception:                               # noqa: BLE001
            log.exception("Слушатель установки %s упал", self.package.id)

    def _run(self) -> None:
        import subprocess

        try:
            self._say("downloading", f"Ставлю {self.package.title}")
            # Into **our own** interpreter: `sys.executable` is the runtime
            # we shipped, not whatever Python the machine happens to have.
            # Somebody else's installation is not our place to change.
            #
            # The name comes from `PACKAGES`, never from the caller — see
            # `T-20`. This line is the one that would turn a message into
            # code execution if the name came from outside.
            self._process = subprocess.Popen(
                [sys.executable, "-m", "pip", "install",
                 "--disable-pip-version-check", "--no-input",
                 self.package.pip],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace")

            tail = []
            for line in self._process.stdout:
                if self._stop.is_set():
                    break
                said = line.strip()
                if not said:
                    continue
                tail.append(said)
                del tail[:-6]
                self._say("downloading", said[:120])

            code = self._process.wait()
            if self._stop.is_set():
                self._say("cancelled")
                return

            # Whether it worked is decided by asking Python, not by the exit
            # code: `pip` returns zero for "already satisfied" and for
            # installs that leave nothing importable on this interpreter.
            # The question is "can the core import it now", and that is the
            # only question the person cares about.
            import importlib

            importlib.invalidate_caches()
            if have_package(self.package):
                log.info("Пакет %s поставлен", self.package.pip)
                self._say("ready")
                return

            self.error = "\n".join(tail[-3:]) or f"pip завершился с {code}"
            self._say("failed")
        except Exception as exc:                        # noqa: BLE001
            self.error = str(exc)
            log.warning("Пакет %s не поставился: %s", self.package.pip, exc)
            self._say("failed")


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
        #: What was last said about this download.
        #:
        #: Kept, so that a window opened **during** one can be told where it
        #: is. Without this, the settings page opened halfway through a
        #: download showed the model as simply "not installed" — and offered
        #: to start a second one.
        self.state = "waiting"
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
        """
        Tell whoever is listening where we are.

        **A listener that throws is not a failed download.** This is called
        from inside the transfer's own `try`, so a mistake in the code that
        *reports* progress came back to the person as "the model could not
        be downloaded" — which is what happened the first time: a missing
        import in the server turned every download into a failure, and the
        error named the download rather than the bug.
        """
        self.state = state
        if self.on_progress is None:
            return
        try:
            self.on_progress({
                "id": self.model.id,
                "state": state,
                "done": self.done,
                "total": self.total,
                "error": self.error,
            })
        except Exception:                               # noqa: BLE001
            log.exception("Слушатель прогресса %s упал", self.model.id)

    def _run(self) -> None:
        if self.model.files:
            self._run_files()
            return

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

    def _run_files(self) -> None:
        """
        A model that is loose files rather than an archive.

        Piper's voice is an `.onnx` and the `.onnx.json` beside it, and
        there is no zip to unpack. The setting is pointed at the first file,
        because that is what the engine is given; the second has to lie next
        to it under the name the first has plus `.json`, which is what the
        server already calls it.

        Everything is downloaded into a folder of its own and only then
        counted as ready. A half-written voice next to a whole settings file
        looks exactly like a finished pair, and the failure surfaces at the
        first word spoken rather than here.
        """
        target = os.path.join(models_dir(), self.model.id)
        holding = target + ".part"
        try:
            self._tidy(holding)
            os.makedirs(holding, exist_ok=True)
            self._say("downloading")

            # The total is the catalogue's until the servers say otherwise,
            # and they are asked one at a time — so the sum is corrected as
            # we go rather than promised up front and then broken.
            got_before = 0
            for url in self.model.files:
                name = url.rsplit("/", 1)[-1]
                with urllib.request.urlopen(url, timeout=60) as answer:
                    with open(os.path.join(holding, name), "wb") as file:
                        while not self._stop.is_set():
                            block = answer.read(self.BLOCK)
                            if not block:
                                break
                            file.write(block)
                            self.done = got_before + (
                                file.tell())
                            self._say("downloading")
                got_before = self.done
                if self._stop.is_set():
                    break

            if self._stop.is_set():
                self._tidy(holding)
                self._say("cancelled")
                return

            self._tidy(target)
            os.rename(holding, target)

            if self.model.setting and self.settings is not None:
                first = self.model.files[0].rsplit("/", 1)[-1]
                self.settings.set(self.model.setting,
                                  os.path.join(target, first))
                self.settings.save()

            log.info("Модель %s готова: %s", self.model.id, target)
            self._say("ready")
        except Exception as exc:                        # noqa: BLE001
            self.error = str(exc)
            self._tidy(holding)
            log.warning("Модель %s не скачалась: %s", self.model.id, exc)
            self._say("failed")

    @staticmethod
    def _tidy(path: str) -> None:
        # A folder as well as a file: a model that is loose files is
        # gathered in a folder of its own, and a half-gathered one has to
        # go the same way a half-written archive does.
        try:
            if os.path.isdir(path):
                shutil.rmtree(path, ignore_errors=True)
            elif os.path.exists(path):
                os.remove(path)
        except OSError:
            pass
