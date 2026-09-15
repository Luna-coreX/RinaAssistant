# -*- coding: utf-8 -*-
"""
I01: the built release starts — with the interpreter we shipped.

Plan item `4.0-I01`; the decision about the runtime is
[ADR 0011](../docs/adr/0011-python-runtime.md).

**An installer that installs something broken is the worst kind: it looks
successful.** The build finishes with a zero exit code exactly the same way
whether all is well or half the runtime failed to arrive; the difference
shows only on the person's machine, and shows as "the program does not
start".

So what is checked is not the layout but the **behaviour**: the core is
raised by `runtime/python/python.exe` from the release, and carried with it
as far as a handshake over the wire. "The file is there" and "the file
works" are different statements, and checking the first is pointless.

The promise of ADR 0011, for whose sake the embedded distribution was
chosen, is checked as well: **a package can be installed into the runtime
we shipped**. Without that the choice loses its main argument, and the
person who decides to install Vosk is the first to find out.

The store is moved into a temporary folder: a release check that writes
into the person's real settings is the same trouble the sandbox guards
against.

To run:
    python tools/check_release.py                  dist/Rina
    python tools/check_release.py build/try        another folder
"""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
os.chdir(ROOT)

from console import use_utf8, child_env
use_utf8()

from core.wire import (Envelope, FrameDecoder, IdGenerator, MessageType,
                       Session, Side, encode_frame)

#: The same version as the one nailed into the build. Two copies of the
#: number would drift apart, and the check would stop checking the very
#: thing that was built.
from build_release import PYTHON_VERSION

fails = 0


def check(label, ok, detail=""):
    global fails
    if not ok:
        fails += 1
    print(("OK   " if ok else "FAIL "), label, detail)


where = os.path.abspath(sys.argv[1] if len(sys.argv) > 1
                        else os.path.join("dist", "Rina"))

print(f"Выпуск: {where}")
print()
print("=== раскладка ===")

if not os.path.isdir(where):
    print(f"FAIL  папки нет | сначала: python tools/build_release.py")
    sys.exit(1)

python = os.path.join(where, "runtime", "python", "python.exe")
entry = os.path.join(where, "rina_core.py")

check("рантайм на месте", os.path.isfile(python), f"| {python}")
check("ядро на месте", os.path.isfile(entry))
for name in ("core", "voice", "plugins"):
    check(f"пакет {name} уехал", os.path.isdir(os.path.join(where, name)))

# The shell is published as a separate step: the build can be run without
# it (`--skip-shell`), so its absence is not a failure but something said
# out loud.
shell = os.path.join(where, "Rina.Shell.exe")
if os.path.isfile(shell):
    check("оболочка на месте", True, f"| {os.path.getsize(shell) // 1024} КБ")
else:
    print("     оболочка не публиковалась (--skip-shell) — проверяем ядро")

# Foreign paths inside a `.pyc` are a trace of the developer's machine
# that travelled to the person.
strays = []
for base, dirs, files in os.walk(where):
    if "__pycache__" in base or "site-packages" in base:
        continue
    strays += [os.path.join(base, f) for f in files if f.endswith(".pyc")]
check("скомпилированного мусора нет", not strays, f"| {strays[:2]}")

if not os.path.isfile(python):
    print()
    print("ИТОГО ошибок:", fails + 1)
    sys.exit(1)

print()
print("=== привезённый интерпретатор — тот самый ===")

said = subprocess.run([python, "-c", "import sys; print(sys.version)"],
                      capture_output=True, text=True, encoding="utf-8",
                      errors="replace", env=child_env())
check("рантайм запускается", said.returncode == 0, f"| {said.stderr.strip()}")
check(f"версия та, что прибита ({PYTHON_VERSION})",
      said.stdout.strip().startswith(PYTHON_VERSION),
      f"| {said.stdout.strip().splitlines()[0] if said.stdout else '—'}")

# It must not be the one installed on the machine: the whole point of
# ADR 0011 is that we brought our own.
own = subprocess.run([python, "-c", "import sys; print(sys.prefix)"],
                     capture_output=True, text=True, encoding="utf-8",
                     errors="replace", env=child_env())
check("это наш рантайм, а не системный",
      os.path.normcase(where) in os.path.normcase(own.stdout.strip()),
      f"| {own.stdout.strip()}")

print()
print("=== собранная Рина слышит речь ===")

# The check whose absence hid everything else. Recognition was implemented,
# checked in the core, and installed into the runtime by nobody: for as long
# as this was not asked, every copy of Rina anyone assembled was deaf to
# speech — and not on one machine but on all of them. A person meets that as
# silence, which is the hardest thing to trace back to a build step.
#
# Asked of the **shipped** runtime, in its own words: whether recognition is
# available is a property of that interpreter and the packages in it, and
# the developer's own Python answers a different question.
heard = subprocess.run(
    [python, "-c",
     "import sys; sys.path.insert(0, r'" + where + "');"
     "from core.speech import RECOGNISERS;"
     "from core.settings_api import MemorySettings;"
     "s = MemorySettings({});"
     "ready = [n for n in RECOGNISERS if n != 'disabled'"
     " and RECOGNISERS[n](s).available()];"
     "print(','.join(ready))"],
    capture_output=True, text=True, encoding="utf-8", errors="replace",
    env=child_env())
ready = heard.stdout.strip()
check("распознавание в сборке доступно", bool(ready),
      f"| {ready or heard.stderr.strip()[:120] or 'ни одного движка'}")

# And speech, which had no check at all and was missing for exactly as
# long as it went unasked. The comment above says "a person meets that as
# silence"; for synthesis that is not a figure of speech.
#
# `silent` does not count: it is the lawful choice of having no voice, and
# counting it would make this question answer itself.
spoke = subprocess.run(
    [python, "-c",
     "import sys; sys.path.insert(0, r'" + where + "');"
     "from voice import tts;"
     "print(','.join(e.id for e in tts.available_engines()"
     " if e.id != 'silent'))"],
    capture_output=True, text=True, encoding="utf-8", errors="replace",
    env=child_env())
speaks = spoke.stdout.strip()
check("озвучка в сборке доступна", bool(speaks),
      f"| {speaks or spoke.stderr.strip()[:160] or 'ни одного движка'}")

print()
print("=== в рантайм можно доставить пакет ===")

# The promise of ADR 0011. Without it the choice of an embedded
# distribution loses its main argument: speech engines and plugins'
# dependencies are installed **later**.
pip = subprocess.run([python, "-c", "import pip; print(pip.__version__)"],
                     capture_output=True, text=True, encoding="utf-8",
                     errors="replace", env=child_env())
check("pip на месте и виден рантайму", pip.returncode == 0,
      f"| {pip.stderr.strip()[:120]}")

deps = subprocess.run(
    [python, "-c", "import numpy, soundfile; print(numpy.__version__)"],
    capture_output=True, text=True, encoding="utf-8", errors="replace",
    env=child_env())
check("зависимости ядра импортируются", deps.returncode == 0,
      f"| {deps.stderr.strip()[:160]}")

print()
print("=== ядро поднимается и здоровается ===")

# The settings go into a temporary folder. A release check has no right
# to touch the person's real store.
home = tempfile.mkdtemp(prefix="rina-release-")
core = None
try:
    core = subprocess.Popen(
        [python, "rina_core.py", "--transport", "stdio"],
        cwd=where, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=dict(child_env(), APPDATA=home))

    session = Session(side=Side.SHELL)
    ids = IdGenerator("s-")
    decoder = FrameDecoder()

    hello = Envelope.request("hello", session.hello_payload(), id=ids.next())
    core.stdin.write(encode_frame(hello))
    core.stdin.flush()

    answer, deadline = None, time.monotonic() + 40
    while answer is None and time.monotonic() < deadline:
        if core.poll() is not None:
            break
        chunk = core.stdout.read(1)
        if not chunk:
            break
        for message in decoder.feed(chunk):
            if message.correlation_id == hello.id:
                answer = message

    if answer is None:
        why = (core.stderr.read(4000).decode("utf-8", "replace")
               if core.poll() is not None else "молчит")
        check("ядро ответило на hello", False, f"| {why.strip()[:400]}")
    else:
        check("ядро ответило на hello", answer.type != MessageType.ERROR,
              f"| {answer.payload}")
        session.accept_hello_result(answer.payload)
        check("версия протокола согласована",
              session.ready and (session.version or 0) >= 1,
              f"| v{session.version}")
        check("ядро назвало свою версию",
              bool(answer.payload.get("core_version")),
              f"| {answer.payload.get('core_version')}")
        check("возможности объявлены",
              len(answer.payload.get("capabilities") or []) > 0,
              f"| {answer.payload.get('capabilities')}")
finally:
    if core is not None:
        try:
            core.stdin.close()
        except OSError:
            pass
        try:
            core.wait(timeout=10)
        except subprocess.TimeoutExpired:
            core.kill()
    shutil.rmtree(home, ignore_errors=True)

print()
print("ИТОГО ошибок:", fails)
sys.exit(1 if fails else 0)
