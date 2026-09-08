# -*- coding: utf-8 -*-
"""
I01: build a release — two runtimes and both programs in one folder.

Plan item `4.0-I01`. The decision about the interpreter is
[ADR 0011](../docs/adr/0011-python-runtime.md): an embedded Python
distribution travels with us.

What is built is the layout the installer only has to put on disk:

    Rina/
        Rina.Shell.exe          the shell, self-contained
        runtime/python/         the interpreter and the core's dependencies
        core/  voice/  plugins/ the core
        rina_core.py            the core's entry point

**Why `embed` rather than an unpacked Python installer.** The embedded
distribution is the same CPython without an installer, the registry or
`PATH`. But it is deliberately incomplete: it has no `pip`, no `ensurepip`,
and `site-packages` is switched off by the `._pth` file. All of that is
switched on here, once, at build time — a person who unpacks `embed` by
hand gets **something different**, and this has to be looked at as part of
the build rather than as configuring an environment.

**The core's dependencies are not the 3.1.0 application's.** The first line
of `requirements.txt` is PySide6, and the core does not need it at all:
`rina_core.py` checks that with `check_headless()`. The list below is put
together from what the core actually imports, and it is short — the core
has not one heavy module-level import, and the engines are loaded on
demand.

To run:
    python tools/build_release.py                build everything
    python tools/build_release.py --skip-shell   without .NET (fast)
    python tools/build_release.py --out D:/rina  where to build
"""
import argparse
import io
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
os.chdir(ROOT)

from console import use_utf8, child_env
use_utf8()

#: Which Python travels to the person.
#:
#: The version is nailed down on purpose: "the one we tested against" is a
#: particular number, not a range. Updating the runtime is a release
#: decision, and it has to be made by a person rather than by a build that
#: downloaded today what did not exist yesterday.
PYTHON_VERSION = "3.12.8"
PYTHON_ZIP = (f"https://www.python.org/ftp/python/{PYTHON_VERSION}/"
              f"python-{PYTHON_VERSION}-embed-amd64.zip")

#: `pip` is not part of `embed`; we take the official installer.
GET_PIP = "https://bootstrap.pypa.io/get-pip.py"

#: What the **core** needs, not the 3.1.0 application.
#:
#: A bare core comes up on the standard library alone: everything heavy is
#: imported lazily and every import is wrapped in a "no such engine"
#: refusal. Here is what it works without but noticeably worse: reading
#: sound files for synthesis, and parsing PCM.
CORE_REQUIREMENTS = [
    "numpy>=1.24",
    "soundfile>=0.12",
]

#: What travels from the project tree into the release.
CORE_TREE = ["core", "voice", "plugins"]
CORE_FILES = ["rina_core.py", "version.py"]

#: What must not be in the release.
#:
#: `__pycache__` carries foreign paths inside the `.pyc`; `venv` is not
#: our runtime; `tools` are the checks, and they are for the developer,
#: not for the person.
SKIP_DIRS = {"__pycache__", ".git", "venv", ".venv", "node_modules"}

CACHE = os.path.join(ROOT, "build", "cache")


def say(step, detail=""):
    print(f"  {step:34} {detail}")


def fetch(url, into):
    """Download once and remember: a rebuild must not go to the network."""
    os.makedirs(CACHE, exist_ok=True)
    target = os.path.join(CACHE, os.path.basename(url))
    if os.path.isfile(target) and os.path.getsize(target) > 0:
        say("взято из кэша", os.path.basename(target))
        return target
    say("скачиваем", url)
    with urllib.request.urlopen(url, timeout=120) as response:
        data = response.read()
    with io.open(target, "wb") as f:
        f.write(data)
    return target


def build_shell(out):
    """
    Publish the shell as self-contained.

    Self-contained rather than "requires .NET": a .NET runtime on the
    person's machine is the same dependency we refused in Python's case,
    and refusing one while leaving the other would settle the question by
    half.
    """
    project = os.path.join("shell", "Rina.Shell", "Rina.Shell.csproj")
    command = [
        "dotnet", "publish", project,
        "-c", "Release", "-r", "win-x64",
        "--self-contained", "true",
        "-p:PublishSingleFile=false",
        "-o", out,
    ]
    say("публикуем оболочку", "dotnet publish --self-contained")
    done = subprocess.run(command, capture_output=True, text=True,
                          encoding="utf-8", errors="replace",
                          env=child_env())
    if done.returncode != 0:
        tail = (done.stdout or "")[-1500:] + (done.stderr or "")[-1500:]
        raise SystemExit(f"оболочка не собралась:\n{tail}")


def _enable_site_packages(path_file):
    """
    Switch `site-packages` on in `._pth` and make sure it went on.

    **Parsed line by line rather than by a substring search.** The first
    edition asked `"import site" not in body` — and always got "already
    there", because the file contains `#import site` and a line above it an
    explanation with the words `import site` inside. The patch was not
    applied, the step reported success, and `pip` was installed into a
    folder that is not on the path. Testing for containment where a whole
    line is meant is a way to fix what is not broken and not fix what is.

    The assertion belongs here too: the `embed` layout could have changed,
    and a silently built non-working runtime is worse than one not built at
    all.
    """
    lines = io.open(path_file, encoding="utf-8").read().splitlines()
    out_lines, enabled, has_packages = [], False, False
    for line in lines:
        bare = line.strip()
        if bare in ("#import site", "# import site"):
            out_lines.append("import site")
            enabled = True
            continue
        if bare == "import site":
            enabled = True
        if bare.lower().replace("/", "\\") == "lib\\site-packages":
            has_packages = True
        out_lines.append(line)

    if not enabled:
        out_lines.append("import site")
        enabled = True
    # `site.main()` adds `Lib\site-packages` by itself, but only if it
    # exists by the time it runs. We write it explicitly as well: the paths
    # in `._pth` are checked for existence, a spare line is harmless, and
    # an absent one would be discovered on the person's machine.
    if not has_packages:
        out_lines.insert(max(0, len(out_lines) - 1), "Lib\\site-packages")

    io.open(path_file, "w", encoding="utf-8",
            newline="\n").write("\n".join(out_lines) + "\n")

    written = io.open(path_file, encoding="utf-8").read().splitlines()
    if not any(l.strip() == "import site" for l in written):
        raise SystemExit(f"не удалось включить site в {path_file}")


def build_runtime(out):
    """
    Unpack the embedded Python and complete it.

    Three steps, and not one of them can be skipped: unpack, switch
    `site-packages` on, install `pip`. Skipping the second gives a runtime
    into which nothing can be installed — and that is discovered not here
    but by the person who decided to install Vosk.
    """
    runtime = os.path.join(out, "runtime", "python")
    if os.path.isdir(runtime):
        shutil.rmtree(runtime)
    os.makedirs(runtime, exist_ok=True)

    with zipfile.ZipFile(fetch(PYTHON_ZIP, CACHE)) as archive:
        archive.extractall(runtime)
    say("рантайм распакован", f"Python {PYTHON_VERSION}")

    # `._pth` switches site-packages off: that is exactly what makes
    # `embed` different from an ordinary distribution. The line
    # `import site` switches it on — without it `pip install` succeeds
    # while the import does not find what was installed.
    pth = [n for n in os.listdir(runtime) if n.endswith("._pth")]
    if not pth:
        raise SystemExit("в рантайме нет ._pth — раскладка embed изменилась")
    path_file = os.path.join(runtime, pth[0])
    _enable_site_packages(path_file)
    say("site-packages включён", pth[0])

    python = os.path.join(runtime, "python.exe")
    subprocess.run([python, fetch(GET_PIP, CACHE), "--no-warn-script-location"],
                   check=True, capture_output=True, env=child_env())

    # Installing and being able to call are different things, and they
    # parted company right here: `get-pip.py` finished with a zero exit
    # code having put pip into a folder that was not on the path. We ask
    # the runtime itself rather than the installer.
    seen = subprocess.run([python, "-c", "import pip; print(pip.__version__)"],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", env=child_env())
    if seen.returncode != 0:
        raise SystemExit("pip поставлен, но рантайм его не видит — "
                         f"site-packages не на пути:\n{seen.stderr.strip()}")
    say("pip поставлен", f"версия {seen.stdout.strip()}")

    subprocess.run([python, "-m", "pip", "install", "--no-warn-script-location",
                    *CORE_REQUIREMENTS],
                   check=True, capture_output=True, env=child_env())
    say("зависимости ядра", ", ".join(CORE_REQUIREMENTS))
    return python


def copy_core(out):
    """The core, as sources, as they are."""
    for name in CORE_TREE:
        target = os.path.join(out, name)
        if os.path.isdir(target):
            shutil.rmtree(target)
        shutil.copytree(
            name, target,
            ignore=shutil.ignore_patterns(*SKIP_DIRS, "*.pyc"))
    for name in CORE_FILES:
        shutil.copy2(name, os.path.join(out, name))
    say("ядро скопировано", ", ".join(CORE_TREE + CORE_FILES))


def measure(out):
    total = 0
    for base, dirs, files in os.walk(out):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in files:
            try:
                total += os.path.getsize(os.path.join(base, name))
            except OSError:
                pass
    return total


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=os.path.join("dist", "Rina"))
    parser.add_argument("--skip-shell", action="store_true",
                        help="не публиковать .NET — для быстрой проверки")
    parser.add_argument("--installer", action="store_true",
                        help="требовать установщик: без ISCC — отказ, "
                             "а не молчаливый пропуск")
    args = parser.parse_args(argv)

    out = os.path.abspath(args.out)
    print(f"Сборка выпуска в {out}")
    os.makedirs(out, exist_ok=True)

    if args.skip_shell:
        say("оболочка пропущена", "--skip-shell")
    else:
        build_shell(out)

    build_runtime(out)
    copy_core(out)

    size = measure(out)
    print()
    print(f"Готово: {out}")
    print(f"Размер: {size / 1024 / 1024:.0f} МБ")

    made = wrap_installer(args.installer)
    print()
    if made:
        print(f"Установщик: {made}")
    print("Дальше: python tools/check_release.py "
          f"\"{out}\"  — проверить, что собранное запускается")
    return 0


def wrap_installer(wanted):
    """
    Wrap the layout into an installer, if there is anything to do it with.

    The Inno Setup compiler is a third-party program and may be absent.
    Then the build **neither keeps quiet nor pretends**: the layout is
    built and is fit for use, and the missing step is named together with
    what would fix it. A build that reports "done" where no installer
    appeared is the same lie as a green check of something unchecked.
    """
    script = os.path.join(ROOT, "packaging", "rina.iss")
    if not os.path.isfile(script):
        return ""
    compiler = shutil.which("ISCC") or shutil.which("ISCC.exe")
    if not compiler:
        if wanted:
            raise SystemExit(
                "просили установщик, а компилятора Inno Setup нет.\n"
                "Поставьте https://jrsoftware.org/isdl.php — либо соберите "
                "без него: раскладка уже готова.")
        say("установщик пропущен", "нет ISCC (Inno Setup) — раскладка готова")
        return ""
    say("собираем установщик", os.path.basename(script))
    done = subprocess.run([compiler, script], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=child_env())
    if done.returncode != 0:
        raise SystemExit("установщик не собрался:\n"
                         + (done.stdout or "")[-1200:])
    return os.path.join(ROOT, "dist", "RinaAssistant-4.0.0-setup.exe")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
