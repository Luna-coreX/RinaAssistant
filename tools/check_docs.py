# -*- coding: utf-8 -*-
"""
I05: документация ссылается на то, что существует.

Задача плана `4.0-I05`. Документ гниёт молча и особенным образом: код
ломается заметно, а README продолжает выглядеть правдой ещё год после того,
как перестал ею быть. Единственный читатель, который это заметит, — новый
человек, и заметит он это как «здесь всё врёт».

Прозу проверить нельзя. Зато можно проверить всё, что в прозе выглядит как
обещание:

    ссылка на файл        — файл есть в дереве
    ссылка на картинку    — картинка есть и не пустая
    путь в тексте         — существует
    команда `--check-*`   — объявлена оболочкой
    команда `tools/x.py`  — такой инструмент есть

Дополнительно — то, ради чего задача попала в блок выпуска: **обещанные
документы написаны**. Список ниже — это I05 в машинном виде.

Запуск:
    python tools/check_docs.py
"""
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
os.chdir(ROOT)

from console import use_utf8
use_utf8()

fails = 0


def check(label, ok, detail=""):
    global fails
    if not ok:
        fails += 1
    print(("OK   " if ok else "FAIL "), label, detail)


#: Что обещано задачей `4.0-I05`, и где это лежит.
#:
#: Формулировка задачи — «README, схема слоёв, дизайн-система как документ,
#: как писать плагины, как отлаживать» — списком, а не прозой: иначе
#: «выполнено» решается на глаз.
REQUIRED = {
    "README.md": "README",
    "docs/ARCHITECTURE.md": "схема слоёв",
    "docs/design/SYSTEM.md": "дизайн-система как документ",
    "docs/plugins/WRITING-PLUGINS.md": "как писать плагины",
    "docs/DEBUGGING.md": "как отлаживать",
}

#: Документы, которые сверяются на ссылки.
WATCHED = [
    "README.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "docs/ARCHITECTURE.md",
    "docs/DEBUGGING.md",
    "docs/plugins/WRITING-PLUGINS.md",
    "docs/security/THREAT-MODEL.md",
]

STARTUP = os.path.join("shell", "Rina.Shell", "Startup.cs")

print("=== обещанное написано ===")
for path, what in REQUIRED.items():
    ok = os.path.isfile(path) and os.path.getsize(path) > 400
    check(f"{what}: {path}", ok, "" if ok else "| нет файла или он пуст")

print()
print("=== ссылки ведут туда, где что-то есть ===")

# Ссылки markdown: [текст](цель). Внешние и якоря пропускаем — проверять
# сеть значило бы краснеть от чужого сбоя.
LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
IMG = re.compile(r'<img\s+src="([^"]+)"')

for doc in WATCHED:
    if not os.path.isfile(doc):
        check(f"{doc} на месте", False)
        continue
    text = io.open(doc, encoding="utf-8").read()
    base = os.path.dirname(doc)

    for target in LINK.findall(text) + IMG.findall(text):
        target = target.split("#")[0].strip()
        if not target or target.startswith(("http://", "https://", "mailto:")):
            continue
        path = os.path.normpath(os.path.join(base, target))
        check(f"{doc} → {target}", os.path.exists(path), "| нет такого пути")

print()
print("=== картинки настоящие ===")

# Пустой или крошечный PNG — след неудачного снимка. Он выглядит как
# ссылка, которая работает, и потому хуже отсутствующей.
for doc in WATCHED:
    if not os.path.isfile(doc):
        continue
    text = io.open(doc, encoding="utf-8").read()
    base = os.path.dirname(doc)
    for target in IMG.findall(text):
        if target.startswith("http"):
            continue
        path = os.path.normpath(os.path.join(base, target))
        if not os.path.isfile(path):
            continue
        check(f"{target} не пустышка", os.path.getsize(path) > 2000,
              f"| {os.path.getsize(path)} байт")

print()
print("=== план не ссылается на исчезнувшее ===")

# План читают чаще всех и правят чаще всех, поэтому гниёт он первым.
# Проверяются только **закрытые** задачи: у открытой файл и не должен
# существовать, она про будущее.
#
# Имя ищется по дереву, а не по буквальному пути: в плане пишут
# `Platform/Journal.cs`, а лежит он в `shell/Rina.Shell/Platform/`. Строгая
# сверка пути краснела бы на прозе, а не на гнили.
#: `archive/` из обхода не исключается нарочно: перенос в архив не делает
#: прозу о прошлом ложью. Задача, рассказывающая, что чинили в
#: `voice/service.py`, остаётся правдой и после того, как файл уехал
#: туда, — а вот исчезнувший бесследно файл проверка поймает.
SKIP_TREE = {".git", "obj", "bin", "__pycache__", "venv", "dist", "build",
             "node_modules"}
tree = {}
for base, dirs, files in os.walk("."):
    dirs[:] = [d for d in dirs if d not in SKIP_TREE]
    for name in files:
        tree.setdefault(name, []).append(
            os.path.join(base, name).replace("\\", "/")[2:])

roadmap = io.open(os.path.join("docs", "ROADMAP.md"), encoding="utf-8").read()
chunks = re.split(r"^\*\*((?:4\.0|4\.0b|5\.0|N|V)-[A-Za-z0-9]+)\s*·\s*([^*]+)\*\*",
                  roadmap, flags=re.M)

#: Пути, которых нет и не должно быть. Поимённо и с причиной.
#:
#: Не всякое имя файла в плане — обещание. Бывает рассказ о том, что файл
#: переехал, и разбор чужой библиотеки, которую мы отвергли: там имя
#: принадлежит истории или соседу, а не нашему дереву. Список короткий и
#: с объяснениями нарочно — молчаливое исключение превращает правило в
#: пожелание.
NOT_OURS = {
    ("4.0-E05", "core/wire/trace.py"):
        "рассказ о переезде: файл теперь core/trace.py",
    ("4.0-F01b", "Button.xaml"):
        "внутренности WPF-UI — библиотеки, которую отвергли",
}

stale = []
for i in range(1, len(chunks) - 1, 3):
    task, body = chunks[i], chunks[i + 2]
    if "ВЫПОЛНЕНО" not in body.split("\n")[0]:
        continue
    named = set(re.findall(
        r"`([A-Za-z0-9_./\\-]+\.(?:py|cs|xaml|json|iss))`", body))
    for path in named:
        path = path.replace("\\", "/").lstrip("./")
        if os.path.exists(path):
            continue
        tail = path.split("/")[-1]
        if any(hit.endswith(path) for hit in tree.get(tail, [])):
            continue
        if (task, path) in NOT_OURS:
            continue
        stale.append((task, path))

check("закрытые задачи ссылаются на существующее", not stale,
      "| " + ", ".join(f"{t}: {p}" for t, p in stale[:4]))

# И обратно: исключение, переставшее быть нужным, — это забытая строка,
# которая однажды прикроет настоящую гниль.
for (task, path), why in sorted(NOT_OURS.items()):
    tail = path.split("/")[-1]
    exists = os.path.exists(path) or any(
        hit.endswith(path) for hit in tree.get(tail, []))
    check(f"исключение {task}: {path} ещё нужно", not exists,
          f"| файл появился — исключение пора убрать ({why})")

print()
print("=== названные команды существуют ===")

startup = io.open(STARTUP, encoding="utf-8").read()
declared = set(re.findall(r'"(--check-[a-z]+)"', startup))

mentioned_modes, mentioned_tools = set(), set()
for doc in WATCHED:
    if not os.path.isfile(doc):
        continue
    text = io.open(doc, encoding="utf-8").read()
    mentioned_modes.update(re.findall(r"`(--check-[a-z]+)`", text))
    mentioned_modes.update(re.findall(r"\s(--check-[a-z]+)", text))
    mentioned_tools.update(re.findall(r"(tools/[a-z_]+\.py)", text))

for mode in sorted(mentioned_modes):
    check(f"режим {mode} объявлен оболочкой", mode in declared,
          "| документ обещает то, чего оболочка не умеет")

for tool in sorted(mentioned_tools):
    check(f"инструмент {tool} на месте", os.path.isfile(tool))

print()
print("=== README говорит о нынешней версии ===")

readme = io.open("README.md", encoding="utf-8").read()

# Версий четыре (ADR 0004), и сверять README надо с версией **продукта** —
# то есть оболочки. `version.py` описывает приложение 3.1.0, которое живёт
# рядом, и сверка с ним говорила бы неправду.
#
# Разбор, который ничего не нашёл, — это провал, а не пропуск. Первая
# редакция этой проверки искала `__version__`, которого в проекте нет, и
# молча зеленела: `if current:` пропускал утверждение целиком. Проверка,
# умеющая пропустить себя, хуже отсутствующей — на неё полагаются.
props = io.open(os.path.join("shell", "Directory.Build.props"),
                encoding="utf-8").read()
found = re.search(r"<Version>([^<]+)</Version>", props)
check("версия оболочки читается", found is not None,
      "| нечего сверять с README")
if found:
    shell_version = found.group(1)
    major = shell_version.split(".")[0]
    check(f"версия в README совпадает с оболочкой ({shell_version})",
          f"Version {major}." in readme,
          "| README пережил смену версии, и это заметит только новый человек")

# Скриншоты 3.0.0 сняты с программы, которой больше нет. Ссылка на них —
# не мёртвая ссылка, а живая ложь: картинка откроется.
check("старых скриншотов в README нет",
      not re.search(r"docs/0\d-\w+\.png", readme),
      "| это интерфейс, которого больше не существует")

print()
print("ИТОГО ошибок:", fails)
sys.exit(1 if fails else 0)
