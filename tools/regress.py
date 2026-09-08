# -*- coding: utf-8 -*-
"""
Полный регресс: один вызов, один отчёт (задача плана 4.0-I04).

Проверок к рубежу набралось около тридцати, и каждая запускается своим
именем. Пока их было пять, это работало; на тридцати перестаёт — не потому,
что тяжело, а потому, что надо **помнить**. Проверка, о которой забыли,
неотличима от отсутствующей: сессии с записанным поведением были красными
неделю, и узнали об этом случайно.

Что здесь есть, кроме удобства.

**Список проверок выводится, а не пишется руками.** Всякий `tools/test_*.py`
и `tools/check_*.py` — проверка; порождатели проверяются своим `--check`;
режимы оболочки читаются из `Startup.cs`. Написанный руками перечень
разошёлся бы с каталогом на первой же новой проверке — ровно так, как это
уже записано про каталог ошибок в `test_wire.py`.

**То, что не проверка, названо поимённо и с причиной.** Иначе «выводится»
превращается в «выводится, кроме того, что забыли»: файл, выпавший из
обеих категорий, проходил бы молча. Регресс на таком падает.

**Пропуск виден и считается.** Проверке оболочки нужен `dotnet`; если его
нет, честнее сказать «пропущено», чем показать зелёный итог. `--strict`
делает пропуск ошибкой — для сборочной линии, где пропускать нечего.

**Что трогает машину, отделено.** `--check-voice` говорит вслух,
`--check-hover` водит мышью, `--check-tray` заводит значок. Их место в
группе `машина`, и по умолчанию они не идут: регресс, который посреди
работы начинает говорить и двигать курсор, запускают один раз.

Запуск:
    python tools/regress.py               ядро и оболочка
    python tools/regress.py --group ядро  только питон, без dotnet
    python tools/regress.py --all         вместе с тем, что трогает машину
    python tools/regress.py --strict      пропуск считается ошибкой
    python tools/regress.py --list        только показать, что будет запущено
"""
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
os.chdir(ROOT)

from console import child_env, use_utf8
use_utf8()

TOOLS = os.path.join(ROOT, "tools")
SHELL_PROJECT = os.path.join("shell", "Rina.Shell", "Rina.Shell.csproj")
STARTUP = os.path.join("shell", "Rina.Shell", "Startup.cs")


# ---------------------------------------------------------------------------
# Что не является проверкой
# ---------------------------------------------------------------------------
#: Поимённо и с причиной.
#:
#: Список нужен не для порядка, а чтобы «выводится» осталось правдой. Файл,
#: который не проверка и здесь не назван, — это либо забытая проверка, либо
#: забытое объяснение; и то и другое стоит того, чтобы регресс покраснел.
NOT_A_CHECK = {
    "_core_sandboxed.py": "запускатель ядра под песочницей, не проверка",
    "build_mockups.py": "собирает макеты, ничего не сверяет",
    "build_release.py": "собирает выпуск; сверяет его check_release.py",
    "console.py": "общая мелочь: вывод в UTF-8",
    "regress.py": "этот файл",
    "retranslate.py": "правит комментарии по заданию",
    "sandbox.py": "песочница, которой пользуются проверки",
    "voice_bench.py": "стенд замеров: меряет, а не проверяет",
}

#: Проверки, которым нужен собранный выпуск, и где он лежит.
#:
#: Собирать выпуск внутри регресса нельзя: это минуты, сеть и четверть
#: гигабайта на диске. Но и молчать о непроверенном установщике нельзя,
#: поэтому без выпуска проверка не исчезает, а становится «пропущено» с
#: указанием, чем это чинится.
NEEDS_RELEASE = {
    "check_release.py": os.path.join(ROOT, "dist", "Rina"),
}

#: Порождатели: проверка у них — сверить порождённое с источником.
GENERATORS = ("gen_csharp_contract.py", "gen_shell_strings.py",
              "gen_xaml_tokens.py")

#: Проверки, которые зовутся не по имени файла.
BY_HAND = {
    "session.py": ["--replay-all"],
    # Сверке по пикселям нужен снимок, а снимок делает сама оболочка. Она в
    # группе «снимок» и собирается из двух шагов — см. `render_checks`.
    "check_shell_render.py": None,
}

#: Отделки, каждая со своим снимком.
#:
#: Обе равноправны (`4.0-R08`), и проверять одну значило бы проверять
#: половину: значения у них разные, и разойтись они могут порознь.
FINISHES = ("silver", "black")

#: Режимы оболочки, которые трогают машину или человека.
#:
#: Не «медленные» и не «капризные»: они говорят вслух, водят мышью и заводят
#: значок в трее. Регресс, делающий это без спроса посреди рабочего дня,
#: перестают запускать — и тогда он не проверяет ничего.
TOUCHES_MACHINE = {"--check-voice", "--check-hover", "--check-tray",
                   "--check-audio", "--check-system"}


class Check:
    """Одна проверка: как её зовут, чем запускают и к какой группе она."""

    def __init__(self, name, group, command, note="", skip=""):
        self.name = name
        self.group = group
        self.command = command
        self.note = note
        #: Непустое — проверку не запускаем, а называем причину. Пропуск
        #: должен объяснять себя сам: строка «пропущено» без «почему»
        #: читается как «сломано, но мы не смотрели».
        self.skip = skip


def python_checks():
    """`tools/test_*.py`, `tools/check_*.py` и порождатели со сверкой."""
    found = []
    for name in sorted(os.listdir(TOOLS)):
        if not name.endswith(".py"):
            continue
        path = os.path.join("tools", name)
        if name in NOT_A_CHECK:
            continue
        if name in GENERATORS:
            found.append(Check(name, "ядро",
                               [sys.executable, path, "--check"],
                               "порождённое сходится с источником"))
            continue
        if name in BY_HAND:
            args = BY_HAND[name]
            if args is None:
                continue
            found.append(Check(name, "ядро", [sys.executable, path] + args))
            continue
        if name in NEEDS_RELEASE and not os.path.isdir(NEEDS_RELEASE[name]):
            # Выпуска нет — проверять нечего, и это «пропущено», а не
            # «успех»: зелёная строка про непроверенный установщик хуже
            # красной, потому что ей верят.
            found.append(Check(name, "выпуск", [sys.executable, path],
                               skip="нет dist/Rina — "
                                    "python tools/build_release.py"))
            continue
        if name.startswith(("test_", "check_")) or name in (
                "conformance.py", "golden_runner.py"):
            found.append(Check(name, "ядро", [sys.executable, path]))
    return found


def unclassified():
    """
    Файлы, которые не проверка и не названы таковыми.

    Это и есть цена вывода списка: без такой сверки «выводится» означает
    «выводится то, что подошло под шаблон», и новый инструмент с непривычным
    именем выпадает молча.
    """
    known = {c.name for c in python_checks()}
    out = []
    for name in sorted(os.listdir(TOOLS)):
        if not name.endswith(".py") or name in NOT_A_CHECK or name in known:
            continue
        if name in BY_HAND:            # названа отдельно, см. группу «снимок»
            continue
        out.append(name)
    return out


def shell_modes():
    """Режимы `--check-*`, объявленные самой оболочкой."""
    text = io.open(STARTUP, encoding="utf-8").read()
    return sorted(set(re.findall(r'"(--check-[a-z]+)"', text)))


def shell_checks():
    found = []
    for mode in shell_modes():
        group = "машина" if mode in TOUCHES_MACHINE else "оболочка"
        found.append(Check(mode, group,
                           ["dotnet", "run", "--project", SHELL_PROJECT,
                            "--", mode]))
    return found


def render_checks(shots_dir):
    """
    Нарисованное окно против токенов — в два шага.

    Снимок делает сама оболочка (`--shot`), сверяет по точкам
    `check_shell_render.py`. Двумя шагами потому, что рисует и меряет разное:
    рисует WPF, меряет питон, и связать их можно только через файл.
    """
    found = []
    for finish in FINISHES:
        png = os.path.join(shots_dir, f"{finish}.png")
        found.append(Check(f"снимок {finish}", "снимок",
                           ["dotnet", "run", "--project", SHELL_PROJECT,
                            "--", "--shot", png, "--finish", finish]))
        found.append(Check(f"сверка {finish}", "снимок",
                           [sys.executable,
                            os.path.join("tools", "check_shell_render.py"),
                            png, finish]))
    return found


def all_checks(shots_dir):
    return python_checks() + shell_checks() + render_checks(shots_dir)


# ---------------------------------------------------------------------------
# Прогон
# ---------------------------------------------------------------------------
def run(check, timeout):
    """Запустить и вернуть (исход, секунды, последняя внятная строка)."""
    if check.skip:
        return "пропущено", 0.0, check.skip
    started = time.monotonic()
    try:
        done = subprocess.run(check.command, capture_output=True, text=True,
                              encoding="utf-8", errors="replace",
                              env=child_env(), timeout=timeout)
    except FileNotFoundError:
        return "пропущено", 0.0, f"нет {check.command[0]}"
    except subprocess.TimeoutExpired:
        return "провал", time.monotonic() - started, f"не уложилась в {timeout} с"

    spent = time.monotonic() - started
    tail = ""
    for line in reversed((done.stdout or "").splitlines()):
        if line.strip():
            tail = line.strip()
            break
    return ("успех" if done.returncode == 0 else "провал"), spent, tail


def main(argv):
    wanted = {"ядро", "оболочка", "снимок"}
    if "--all" in argv:
        wanted.add("машина")
    if "--group" in argv:
        wanted = {argv[argv.index("--group") + 1]}
    strict = "--strict" in argv

    # Снимки — во временную папку: регресс не должен оставлять после себя
    # картинок в дереве проекта.
    shots = tempfile.mkdtemp(prefix="rina-regress-")
    stray = unclassified()
    checks = [c for c in all_checks(shots) if c.group in wanted]

    if "--list" in argv:
        for c in checks:
            print(f"  {c.group:9} {c.name}")
        print(f"\nвсего: {len(checks)}")
        return 0

    print("=== полный регресс (4.0-I04) ===")
    print(f"    групп: {', '.join(sorted(wanted))}, проверок: {len(checks)}")
    print()

    failed, skipped, spent_total = [], [], 0.0
    for c in checks:
        # Оболочке нужно поднять ядро и подождать связи; питону — нет.
        timeout = 600 if c.group != "ядро" else 300
        verdict, spent, tail = run(c, timeout)
        spent_total += spent
        mark = {"успех": "OK  ", "провал": "FAIL", "пропущено": "----"}[verdict]
        print(f"  {mark}  {c.name:26} {spent:6.1f} с  {tail[:60]}")
        if verdict == "провал":
            failed.append(c.name)
        elif verdict == "пропущено":
            skipped.append(f"{c.name} ({tail})")

    print()
    if stray:
        print("НЕ РАЗОБРАНО: файлы, которые не проверка и не названы таковыми")
        for name in stray:
            print(f"    {name}")
        print("    добавьте в NOT_A_CHECK с причиной — или назовите проверкой")
        print()

    print(f"Проверок: {len(checks)}, провалов: {len(failed)}, "
          f"пропущено: {len(skipped)}, за {spent_total:.0f} с")
    for name in failed:
        print(f"    провал: {name}")
    for name in skipped:
        print(f"    пропущено: {name}")
    if skipped and not strict:
        print("    пропуск не считается ошибкой; --strict сделает его ею")

    shutil.rmtree(shots, ignore_errors=True)
    bad = bool(failed) or bool(stray) or (strict and skipped)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
