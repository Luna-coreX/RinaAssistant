# -*- coding: utf-8 -*-
"""
I01: собрать выпуск — два рантайма и обе программы в одной папке.

Задача плана `4.0-I01`. Решение по интерпретатору —
[ADR 0011](../docs/adr/0011-python-runtime.md): встроенный дистрибутив
Python едет с нами.

Собирается раскладка, которую установщику остаётся положить на диск:

    Rina/
        Rina.Shell.exe          оболочка, самодостаточная
        runtime/python/         интерпретатор и зависимости ядра
        core/  voice/  plugins/ ядро
        rina_core.py            точка входа ядра

**Почему `embed`, а не распакованный установщик Python.** Встроенный
дистрибутив — это тот же CPython без установщика, реестра и `PATH`. Но он
неполон нарочно: в нём нет `pip`, нет `ensurepip`, а `site-packages`
выключен файлом `._pth`. Всё это включается здесь, один раз, при сборке —
человек, распаковавший `embed` руками, получит **не то же самое**, и на
это надо смотреть как на часть сборки, а не как на настройку среды.

**Зависимости ядра — не зависимости приложения 3.1.0.** В `requirements.txt`
первой строкой стоит PySide6, и ядру он не нужен вовсе: `rina_core.py`
проверяет это `check_headless()`. Список ниже собран из того, что ядро
действительно импортирует, и он короткий — тяжёлых импортов на уровне
модуля в ядре нет ни одного, движки подгружаются по надобности.

Запуск:
    python tools/build_release.py                собрать всё
    python tools/build_release.py --skip-shell   без .NET (быстро)
    python tools/build_release.py --out D:/rina  куда собрать
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

#: Какой Python едет к человеку.
#:
#: Версия прибита нарочно: «тот, на котором проверяли» — это конкретный
#: номер, а не диапазон. Обновление рантайма — решение выпуска, и принимать
#: его должен человек, а не сборка, скачавшая сегодня то, чего вчера не
#: было.
PYTHON_VERSION = "3.12.8"
PYTHON_ZIP = (f"https://www.python.org/ftp/python/{PYTHON_VERSION}/"
              f"python-{PYTHON_VERSION}-embed-amd64.zip")

#: `pip` в `embed` не входит; берём официальный установщик.
GET_PIP = "https://bootstrap.pypa.io/get-pip.py"

#: Что нужно **ядру**, а не приложению 3.1.0.
#:
#: Голое ядро поднимается и на стандартной библиотеке: всё тяжёлое
#: импортируется лениво и каждый импорт обёрнут отказом «движка нет».
#: Здесь — то, без чего работает, но заметно хуже: чтение звуковых файлов
#: для синтеза и разбор PCM.
CORE_REQUIREMENTS = [
    "numpy>=1.24",
    "soundfile>=0.12",
]

#: Что уезжает из дерева проекта в выпуск.
CORE_TREE = ["core", "voice", "plugins"]
CORE_FILES = ["rina_core.py", "version.py"]

#: Чего в выпуске быть не должно.
#:
#: `__pycache__` — чужие пути внутри `.pyc`; `venv` — не наш рантайм;
#: `tools` — проверки, они разработчику, а не человеку.
SKIP_DIRS = {"__pycache__", ".git", "venv", ".venv", "node_modules"}

CACHE = os.path.join(ROOT, "build", "cache")


def say(step, detail=""):
    print(f"  {step:34} {detail}")


def fetch(url, into):
    """Скачать один раз и запомнить: пересборка не должна ходить в сеть."""
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
    Опубликовать оболочку самодостаточной.

    Самодостаточной, а не «требует .NET»: рантайм .NET на машине человека —
    та же зависимость, от которой мы отказались в случае Python, и
    отказываться от одной, оставляя другую, значило бы решить вопрос
    наполовину.
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
    Включить `site-packages` в `._pth` и убедиться, что включилось.

    **Разбирается построчно, а не поиском подстроки.** Первая редакция
    спрашивала `"import site" not in body` — и всегда получала «уже есть»,
    потому что в файле стоит `#import site`, а строкой выше пояснение со
    словами `import site` внутри. Патч не применялся, шаг рапортовал успех,
    и `pip` вставал в папку, которой нет на пути. Проверять вхождение там,
    где речь о строке целиком, — способ починить то, что не сломано, и не
    починить то, что сломано.

    Здесь же и утверждение: раскладка `embed` могла измениться, и молча
    собранный нерабочий рантайм хуже несобранного.
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
    # `site.main()` добавляет `Lib\site-packages` сам, но только если она
    # существует к моменту запуска. Пишем её и явно: пути в `._pth`
    # проверяются на существование, лишняя строка безвредна, а отсутствие
    # обнаружится у человека.
    if not has_packages:
        out_lines.insert(max(0, len(out_lines) - 1), "Lib\\site-packages")

    io.open(path_file, "w", encoding="utf-8",
            newline="\n").write("\n".join(out_lines) + "\n")

    written = io.open(path_file, encoding="utf-8").read().splitlines()
    if not any(l.strip() == "import site" for l in written):
        raise SystemExit(f"не удалось включить site в {path_file}")


def build_runtime(out):
    """
    Распаковать встроенный Python и доукомплектовать его.

    Три шага, и ни один нельзя пропустить: распаковать, включить
    `site-packages`, поставить `pip`. Пропущенный второй даёт рантайм, в
    который нельзя ничего доставить, — и обнаружится это не здесь, а у
    человека, который решил поставить Vosk.
    """
    runtime = os.path.join(out, "runtime", "python")
    if os.path.isdir(runtime):
        shutil.rmtree(runtime)
    os.makedirs(runtime, exist_ok=True)

    with zipfile.ZipFile(fetch(PYTHON_ZIP, CACHE)) as archive:
        archive.extractall(runtime)
    say("рантайм распакован", f"Python {PYTHON_VERSION}")

    # `._pth` выключает site-packages: это и есть то, чем `embed`
    # отличается от обычного дистрибутива. Строка `import site` его
    # включает — без неё `pip install` отработает, а импорт не найдёт
    # поставленного.
    pth = [n for n in os.listdir(runtime) if n.endswith("._pth")]
    if not pth:
        raise SystemExit("в рантайме нет ._pth — раскладка embed изменилась")
    path_file = os.path.join(runtime, pth[0])
    _enable_site_packages(path_file)
    say("site-packages включён", pth[0])

    python = os.path.join(runtime, "python.exe")
    subprocess.run([python, fetch(GET_PIP, CACHE), "--no-warn-script-location"],
                   check=True, capture_output=True, env=child_env())

    # Поставить и суметь позвать — разные вещи, и разошлись они здесь же:
    # `get-pip.py` отработал с нулевым кодом, положив pip в папку, которой
    # не было на пути. Спрашиваем сам рантайм, а не установщик.
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
    """Ядро — исходниками, как есть."""
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
    Завернуть раскладку в установщик, если есть чем.

    Компилятор Inno Setup — сторонняя программа, и её может не быть. Тогда
    сборка **не молчит и не притворяется**: раскладка собрана и годится,
    а недостающий шаг назван вместе с тем, чем он чинится. Сборка,
    сообщающая «готово» там, где установщика не появилось, — это то же
    самое враньё, что зелёная проверка непроверенного.
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
