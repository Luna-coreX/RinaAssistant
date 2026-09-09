# -*- coding: utf-8 -*-
"""
4.0b-A14: the setup wizard — the side the core answers for.

The window itself is a matter for the shell; here is what it stands on, and
what a shell cannot get right on its own: whether this is a first run, that
saying so once is enough and survives a restart, and that the catalogue
offers the small model ready-ticked and the two-gigabyte one not.

Through a live core over the real protocol, and with a profile of its own.
Answering out of the developer's settings would say "not a first run" on the
one machine this is ever run on, and pass for the wrong reason.
"""
import os
import sys
import shutil
import tempfile
import time

sys.path.insert(0, r"C:\DevStation\PCDev\DesktopApps\RinaAssistant")
sys.path.insert(0, os.path.join(
    r"C:\DevStation\PCDev\DesktopApps\RinaAssistant", "tools"))

from console import use_utf8
from coreproc import Core

use_utf8()

fails = 0


def check(label, cond, detail=""):
    global fails
    if not cond:
        fails += 1
    print(("OK   " if cond else "FAIL "), label, detail)


def answer(core, method, payload=None):
    """
    Ask, and give back the reply's payload.

    One message at a time. `read` blocks on the pipe and only looks at its
    deadline between messages, so asking it for six when one is coming waits
    for ever on the seventh — the check hung instead of failing, which is
    the worst way for a check to be wrong.
    """
    sent = core.ask(method, payload or {})
    for _ in range(8):
        got = core.read(1, timeout=15.0)
        if not got:
            break
        if got[0].correlation_id == sent.id:
            return got[0].payload
    return {}


# Cleaned up by hand, and forgivingly. The core opens `audit.db` and
# Windows does not let a file go the instant a process is killed; a
# temporary directory that insists on removing itself turns that into a
# traceback after every check has already passed.
home = tempfile.mkdtemp()
try:
    core = Core(env={"APPDATA": home, "XDG_CONFIG_HOME": home})
    core.handshake()

    print("=== первый запуск ===")
    state = answer(core, "setup.state")
    check("ядро говорит, что это первый запуск",
          state.get("needed") is True, f"| {state}")

    print()
    print("=== каталог ===")
    listed = answer(core, "models.catalogue").get("items", [])
    check("каталог приехал", len(listed) > 0, f"| записей {len(listed)}")

    ticked = [m for m in listed if m.get("wanted")]
    # **By what it costs, not by how many.** The rule was always about size:
    # what is ticked for somebody is a box they do not read, so it has to be
    # small enough that nobody minds having agreed to it. The first version
    # of this check counted to one, which was only ever a rough stand-in —
    # and it went red the moment a package joined the model it is useless
    # without, where two ticks are the right answer.
    weight = sum(m["size"] for m in ticked)
    check("отмеченное по умолчанию весит немного",
          0 < weight < 200 * 1024 * 1024,
          f"| {weight // (1024 * 1024)} МБ: "
          + ", ".join(m["id"] for m in ticked))
    check("ничего крупного среди отмеченного нет",
          all(m["size"] < 200 * 1024 * 1024 for m in ticked),
          "| " + ", ".join(f"{m['id']} {m['size'] // (1024 * 1024)} МБ"
                           for m in ticked))

    heavy = [m for m in listed if m["size"] > 1024 * 1024 * 1024]
    check("тяжёлое есть в списке и не отмечено",
          bool(heavy) and not any(m.get("wanted") for m in heavy),
          "| " + ", ".join(m["id"] for m in heavy))
    # `all()` of nothing is true, and both of these passed while the
    # catalogue was empty and every other line was red. A check that agrees
    # with an empty answer is one that will agree with a broken one.
    check("у всего сказано, наше скачивание или движка",
          bool(listed) and all("ours" in m for m in listed))
    check("и у всего есть размер",
          bool(listed) and all(m.get("size", 0) > 0 for m in listed))

    print()
    print("=== движковое скачивание за наше не выдаётся ===")
    # Whisper fetches its own model; `models.fetch` must not claim to have
    # started it. Saying "started" would leave a window waiting for progress
    # that is never coming, with a stop button that stops nothing.
    started = answer(core, "models.fetch",
                     {"ids": ["whisper-base"]}).get("tasks", [])
    check("движковое не объявлено начатым", started == [], f"| {started}")

    # The rest of the download's behaviour — progress while it runs, the
    # catalogue reporting it, cancelling — is checked in `test_models.py`
    # against a local server. Doing it here would pull forty-six megabytes
    # off somebody else's machine on every run of the regression, and would
    # go red on a train rather than when the code broke.

    print()
    print("=== флаг меняет только завершение мастера ===")
    # The button in "About" opens the same wizard, and opening it must not
    # mark the first run as done: somebody who looked at the wizard out of
    # curiosity would otherwise never be shown it when it matters. So the
    # flag is asked here after everything else the shell might call.
    for method, payload in (("models.catalogue", {}),
                            ("models.fetch", {"ids": ["whisper-base"]}),
                            ("settings.get", {"keys": ["volume"]}),
                            ("setup.state", {})):
        answer(core, method, payload)
    still = answer(core, "setup.state")
    check("после всего прочего он всё ещё первый запуск",
          still.get("needed") is True, f"| {still}")

    print()
    print("=== мастер закрывается насовсем ===")
    answer(core, "setup.finish")
    again = answer(core, "setup.state")
    check("второй раз не показывается", again.get("needed") is False,
          f"| {again}")
    core.proc.kill()

    # And it survives a restart: the answer lives in the settings file
    # rather than in the core's memory. A wizard that came back after every
    # restart would be the same defect as one that never appeared.
    core = Core(env={"APPDATA": home, "XDG_CONFIG_HOME": home})
    core.handshake()
    after = answer(core, "setup.state")
    check("и после перезапуска ядра тоже",
          after.get("needed") is False, f"| {after}")
    core.proc.kill()

finally:
    shutil.rmtree(home, ignore_errors=True)

print()
print("ИТОГО ошибок:", fails)
sys.exit(1 if fails else 0)
