# -*- coding: utf-8 -*-
"""
I01: собранный выпуск запускается — привезённым интерпретатором.

Задача плана `4.0-I01`; решение по рантайму —
[ADR 0011](../docs/adr/0011-python-runtime.md).

**Установщик, который ставит нерабочее, — худший из возможных: он выглядит
успешным.** Сборка отрабатывает с нулевым кодом ровно так же, когда всё
хорошо и когда в рантайм не доехала половина; разницу видно только у
человека, и видно как «программа не запускается».

Поэтому проверяется не раскладка, а **поведение**: ядро поднимается
`runtime/python/python.exe` из выпуска, и с ним доводится до рукопожатия по
проводу. Файл на месте и файл работает — разные утверждения, и первое
проверять бессмысленно.

Проверяется и обещание ADR 0011, ради которого встроенный дистрибутив и
выбран: **в привезённый рантайм можно доставить пакет**. Без этого выбор
теряет главный довод, а человек, решивший поставить Vosk, узнаёт об этом
первым.

Хранилище уводится во временную папку: проверка выпуска, которая пишет в
настоящие настройки человека, — та же беда, от которой бережёт песочница.

Запуск:
    python tools/check_release.py                  dist/Rina
    python tools/check_release.py build/try        другая папка
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

#: Та же версия, что прибита в сборке. Две копии числа разошлись бы, и
#: проверка перестала бы проверять именно то, что собрано.
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

# Оболочка публикуется отдельным шагом: сборку можно гонять и без неё
# (`--skip-shell`), поэтому её отсутствие — не провал, а сказанное вслух.
shell = os.path.join(where, "Rina.Shell.exe")
if os.path.isfile(shell):
    check("оболочка на месте", True, f"| {os.path.getsize(shell) // 1024} КБ")
else:
    print("     оболочка не публиковалась (--skip-shell) — проверяем ядро")

# Чужие пути внутри `.pyc` — след машины разработчика, уехавший к человеку.
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

# Он не должен быть тем, что стоит на машине: весь смысл ADR 0011 в том,
# что мы привезли свой.
own = subprocess.run([python, "-c", "import sys; print(sys.prefix)"],
                     capture_output=True, text=True, encoding="utf-8",
                     errors="replace", env=child_env())
check("это наш рантайм, а не системный",
      os.path.normcase(where) in os.path.normcase(own.stdout.strip()),
      f"| {own.stdout.strip()}")

print()
print("=== в рантайм можно доставить пакет ===")

# Обещание ADR 0011. Без него выбор встроенного дистрибутива теряет
# главный довод: движки речи и зависимости плагинов ставятся **потом**.
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

# Настройки — во временную папку. Проверка выпуска не имеет права трогать
# настоящее хранилище человека.
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
