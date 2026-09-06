# -*- coding: utf-8 -*-
"""
A sandbox for the tests: it disarms EVERY side effect at once.

It appeared after the two-cores test substituted the sound, the system
actions and the launching of programs — and forgot the browser. A phrase the
pipeline did not parse goes to the fallback web search, and real tabs opened
on the developer's machine.

Listing the substitutions by hand in every test means forgetting one again
one day. Here they are gathered in one place, and that is the same place
where the catalogue of side effects from docs/INVENTORY-3.1.0.md, §3 is
kept.

    from tools.sandbox import neutralise
    box = neutralise()          # everything is disarmed
    ...
    box.launched, box.actions, box.opened, box.spoken

**The store is a side effect too, and that came out late.** The
substitutions above covered what is visible from outside — the sound,
launching programs, the browser. But a core raised in a test without
settings of its own took the user's real store and wrote the conversation
history, the call journal and the reminders into it. It was discovered while
preparing 4.0-E05: the reminder scheduler in a test would have created a
reminder in the real list, and it would have fired on a person's machine.

So `neutralise()` first of all moves the data directory into a temporary
folder. The order matters: this has to be done **before** the first store is
created, or it has already remembered the real path.
"""

import atexit
import os
import shutil
import sys
import tempfile


class Recorded:
    """What would have been done had it not been for the sandbox."""

    def __init__(self):
        self.launched = []      # the programs launched
        self.actions = []       # the system actions
        self.opened = []        # the links opened
        self.paths = []         # the files and folders opened
        self.spoken = []        # what was said
        self.reminders = []     # the reminders created

    def clear(self):
        for name in vars(self):
            getattr(self, name).clear()


_isolated = ""


def isolate_storage():
    """
    Move the data directory into a temporary folder. Returns the path.

    Call before the first store is created: the path is computed in
    `core.settings_store._config_dir()` on access, from an environment
    variable, and a store created earlier is already looking at the real
    directory.

    A repeat call does nothing: we isolate once per process.

    `RINA_SANDBOX_DIR` sets the directory from outside — and then it is not
    deleted on exit. That is needed by checks to which it matters what
    survives a **restart** of the core: two processes, each with a temporary
    folder of its own, will pass nothing to each other, and a check that
    settings are preserved would always be green while checking nothing.
    Whoever set the directory clears up after themselves.
    """
    global _isolated
    if _isolated:
        return _isolated

    shared = os.environ.get("RINA_SANDBOX_DIR")
    if shared:
        os.makedirs(shared, exist_ok=True)
        _isolated = shared
    else:
        _isolated = tempfile.mkdtemp(prefix="rina-sandbox-")
        atexit.register(shutil.rmtree, _isolated, True)

    os.environ["APPDATA"] = _isolated
    os.environ["XDG_CONFIG_HOME"] = _isolated
    os.environ["HOME"] = _isolated
    return _isolated


def neutralise(record=None, storage=True):
    """
    Substitutes everything that changes the world. Returns a Recorded.

    The list is deliberately exhaustive: better to substitute something
    superfluous than to open a browser for the user out of a test one day.

    `storage=True` moves the data directory into a temporary folder.
    Switching that off is worth doing only when the store itself is being
    checked — and then the caller is responsible for the path.
    """
    box = record or Recorded()
    if storage:
        isolate_storage()

    # --- sound ---
    from voice import sounds
    sounds.play_response = lambda s: None
    sounds.play_error = lambda s: None
    sounds.play_activation = lambda s: None

    # --- launching programs ---
    from voice import app_index
    app_index.launch = lambda entry: (box.launched.append(entry.name), True)[1]

    # --- system actions ---
    from voice import system_control
    for key in list(system_control.RUNNERS):
        system_control.RUNNERS[key] = (
            lambda k: (lambda: (box.actions.append(k), True)[1]))(key)

    # --- the browser: both the explicit search and the fallback ---
    from voice import websearch
    websearch.webbrowser.open = lambda url, *a, **k: (
        box.opened.append(url), True)[1]

    # --- opening files and folders by user commands ---
    from voice import user_commands
    user_commands._open_path = lambda path: (box.paths.append(path), True)[1]

    # --- speech ---
    from voice import tts
    tts._play_audio_file = lambda path, delete_after=False: True

    # --- the network to the language model ---
    from core import llm
    llm.ask = lambda question, history=None: (_ for _ in ()).throw(
        llm.LLMError("модель в песочнице недоступна"))

    # --- reminders: we record what was asked to be created ---
    # The writing happens all the same, but into a temporary directory (see
    # the header): substituting the store here as well would mean checking
    # the substitution instead of the real scheduler, and that has to stay
    # alive for 4.0-E05.
    from voice import reminders
    real_add = reminders.ReminderStore.add

    def spy_add(store, kind, fire_at, text=""):
        box.reminders.append({"kind": kind, "fire_at": fire_at, "text": text})
        return real_add(store, kind, fire_at, text)

    reminders.ReminderStore.add = spy_add

    return box


def check_sandboxed():
    """
    Makes sure the sandbox is in place. For use at the start of a test.

    Checks the most dangerous thing: that the browser is substituted.
    """
    from voice import websearch

    if getattr(websearch.webbrowser.open, "__module__", "") != __name__:
        raise RuntimeError(
            "песочница не поставлена: вызовите tools.sandbox.neutralise()")
