# -*- coding: utf-8 -*-
"""
I05: the documentation refers to things that exist.

Plan item `4.0-I05`. A document rots silently and in a particular way:
code breaks noticeably, while a README goes on looking true for another
year after it stopped being so. The only reader who will notice is a new
person, and they will notice it as "everything here lies".

Prose cannot be checked. What can be checked is everything in the prose
that looks like a promise:

    a link to a file      — the file is in the tree
    a link to a picture   — the picture exists and is not empty
    a path in the text    — it exists
    a `--check-*` command — the shell declares it
    a `tools/x.py`        — such a tool is there

And on top of that, the thing that put this task into the release block:
**the promised documents have been written**. The list below is I05 in
machine-readable form.

To run:
    python tools/check_docs.py
"""
import io
import os
from urllib.parse import unquote
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


#: What plan item `4.0-I05` promised, and where it lies.
#:
#: The task's wording — "a README, a diagram of the layers, the design
#: system as a document, how to write plugins, how to debug" — as a list
#: rather than prose: otherwise "done" is decided by eye.
REQUIRED = {
    "README.md": "README",
    "docs/ARCHITECTURE.md": "схема слоёв",
    "docs/design/SYSTEM.md": "дизайн-система как документ",
    "docs/plugins/WRITING-PLUGINS.md": "как писать плагины",
    "docs/DEBUGGING.md": "как отлаживать",
}

#: The documents whose links are checked.
WATCHED = [
    "README.md",
    # The plan is the document that promises the most: it names both the
    # shell's modes and the files of the checks. It was not here, and the
    # promise "the named `--check-*` are declared by the shell" rested on
    # the seven documents that make almost no such promises. A made-up
    # mode in the plan passed silently — verified by breaking it.
    "docs/ROADMAP.md",
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

# Markdown links: [text](target). External ones and anchors are skipped —
# checking the network would mean going red at somebody else's outage.
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
        # A space in a file name is written as `%20` in a link — not an
        # ornament but the only way to refer to such a file from markdown.
        # Without decoding it, the check would call a valid link broken —
        # that is, it would demand renaming the file for its own sake.
        path = os.path.normpath(os.path.join(base, unquote(target)))
        check(f"{doc} → {target}", os.path.exists(path), "| нет такого пути")

print()
print("=== картинки настоящие ===")

# An empty or tiny PNG is the trace of a failed screenshot. It looks like
# a link that works, and is therefore worse than a missing one.
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

# The plan is read most often and edited most often, so it rots first.
# Only **closed** items are checked: an open one's file is not supposed to
# exist, it is about the future.
#
# The name is looked for across the tree rather than by a literal path:
# the plan writes `Platform/Journal.cs` while it lies in
# `shell/Rina.Shell/Platform/`. A strict path comparison would go red at
# the prose rather than at the rot.
#: `archive/` is deliberately not excluded from the walk: moving
#: something into the archive does not make prose about the past a lie. An
#: item describing what was fixed in `voice/service.py` stays true after
#: the file has gone there — whereas a file that vanished without trace is
#: something the check will catch.
SKIP_TREE = {".git", "obj", "bin", "__pycache__", "venv", "dist", "build",
             "node_modules"}
tree = {}
for base, dirs, files in os.walk("."):
    dirs[:] = [d for d in dirs if d not in SKIP_TREE]
    for name in files:
        tree.setdefault(name, []).append(
            os.path.join(base, name).replace("\\", "/")[2:])

roadmap = io.open(os.path.join("docs", "ROADMAP.md"), encoding="utf-8").read()
chunks = re.split(r"^\*\*((?:4\.0|4\.0b|4\.0s|5\.0|N|V)-[A-Za-z0-9]+)\s*·\s*([^*]+)\*\*",
                  roadmap, flags=re.M)

#: Paths that do not exist and should not. By name and with a reason.
#:
#: Not every file name in the plan is a promise. There are accounts of a
#: file having moved, and reviews of somebody else's library that we
#: rejected: there the name belongs to history or to a neighbour, not to
#: our tree. The list is short and annotated on purpose — a silent
#: exception turns a rule into a wish.
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

# And the other way round: an exception that has stopped being needed is
# a forgotten line that will one day cover up real rot.
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

# There are four versions (ADR 0004), and the README has to be compared
# with the version of the **product** — that is, of the shell.
# `version.py` describes the 3.1.0 application living alongside, and
# comparing with that would tell an untruth.
#
# A parse that found nothing is a failure, not a skip. The first edition
# of this check looked for `__version__`, which the project does not have,
# and went green silently: `if current:` skipped the assertion entirely. A
# check that can skip itself is worse than no check — it is relied on.
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

# The 3.0.0 screenshots were taken of a program that no longer exists. A
# link to them is not a dead link but a living lie: the picture opens.
check("старых скриншотов в README нет",
      not re.search(r"docs/0\d-\w+\.png", readme),
      "| это интерфейс, которого больше не существует")

# ---------------------------------------------------------------------------
# The numbers the README quotes (`4.0b-C04`)
# ---------------------------------------------------------------------------
#
# A product page is read by somebody deciding whether to try the thing, and
# a number in it is the part they believe without checking. Which is exactly
# how it rots: the code moves, the sentence stays, and the sentence is what
# the reader takes away.
#
# It had rotted. "Eleven system actions" when there were sixteen, "two
# finishes" when there were three, "four surfaces, seventeen threats" when
# there were six and twenty-two, "39 checks" when there were sixty-five.
# None of it was noticed by anybody, because nothing was looking.
import json
import subprocess

print()
print("=== числа, которые называет README ===")


def quoted(word, said):
    """Does the README say this number for this thing?"""
    return said in readme


with io.open(os.path.join(ROOT, "docs", "design", "tokens.json"),
             encoding="utf-8") as handle:
    finishes = len(json.load(handle)["finishes"])

model = io.open(os.path.join(ROOT, "docs", "security", "THREAT-MODEL.md"),
                encoding="utf-8").read()
threats = len(re.findall(r"^### T-", model, re.MULTILINE))
surfaces = len(re.findall(r"^## Поверхность", model, re.MULTILINE))

sys.path.insert(0, ROOT)
from voice.user_commands import COMMAND_TYPES, STEP_ONLY, SYSTEM_ACTIONS

#: Numbers written out as words, because that is how a page for people
#: writes them. A page that said "16 actions" would read like a table.
WORDS = {
    2: "Two", 3: "Three", 4: "Four", 5: "Five", 6: "Six", 7: "Seven",
    11: "Eleven", 16: "Sixteen", 17: "seventeen", 22: "twenty-two",
    23: "twenty-three",
}

check(f"отделок в README столько же, сколько в системе ({finishes})",
      quoted("finishes", f"{WORDS.get(finishes, finishes)} finishes"),
      f"| ждали «{WORDS.get(finishes, finishes)} finishes»")

check(f"системных действий ({len(SYSTEM_ACTIONS)})",
      quoted("actions", f"{WORDS.get(len(SYSTEM_ACTIONS))} actions"),
      f"| ждали «{WORDS.get(len(SYSTEM_ACTIONS))} actions»")

check(f"видов шага ({len(STEP_ONLY)})",
      quoted("steps", f"{WORDS.get(len(STEP_ONLY), '').lower()} more exist"),
      f"| ждали «{WORDS.get(len(STEP_ONLY), '').lower()} more exist»")

check(f"поверхностей и угроз ({surfaces} и {threats})",
      f"{WORDS.get(surfaces)} surfaces" in readme
      and f"{WORDS.get(threats)} threats" in readme,
      f"| ждали «{WORDS.get(surfaces)} surfaces, {WORDS.get(threats)} threats»")

# The number of checks comes from the suite itself: asking it is the only
# way to be sure, and the suite is what the sentence is about.
try:
    listed = subprocess.run(
        [sys.executable, os.path.join(ROOT, "tools", "regress.py"), "--list"],
        capture_output=True, text=True, encoding="utf-8", timeout=120).stdout
    total = re.search(r"всего:\s*(\d+)", listed or "")
    if total:
        check(f"проверок в README столько же, сколько в наборе ({total.group(1)})",
              f"# {total.group(1)} checks" in readme,
              f"| ждали «# {total.group(1)} checks»")
    else:
        check("набор сказал, сколько в нём проверок", False, f"| {listed[-80:]}")
except subprocess.TimeoutExpired:
    check("набор ответил, сколько в нём проверок", False, "| не дождались")

# The size of the golden set, and it had rotted the same way as the rest:
# the README said 112 recorded utterances while the set held 134. The
# sentence is the one that tells a reader how firmly the behaviour is
# pinned down — that is, exactly the sentence a reader has no way of
# checking.
with io.open(os.path.join(ROOT, "docs", "golden", "utterances.json"),
             encoding="utf-8") as handle:
    recorded = len(json.load(handle)["cases"])
sessions = len(os.listdir(os.path.join(ROOT, "docs", "golden", "sessions")))

# Both numbers are named twice in the README, and **every** mention is
# compared rather than any one of them. Breaking this check the first time
# only updated one of the two places and it stayed green — which is the
# half-done edit this whole section exists to catch.
said_cases = set(re.findall(r"(\d+) recorded utterances", readme))
said_cases |= set(re.findall(r"golden set of (\d+) utterances", readme))
check(f"записанных фраз в README столько же, сколько в наборе ({recorded})",
      said_cases == {str(recorded)},
      f"| README называет {sorted(said_cases) or 'ничего'}")

said_sessions = {one.lower()
                 for one in re.findall(r"(\w+) recorded sessions", readme)}
wanted_sessions = str(WORDS.get(sessions, sessions)).lower()
check(f"и записанных сеансов ({sessions})",
      said_sessions == {wanted_sessions},
      f"| ждали «{wanted_sessions} recorded sessions», "
      f"нашли {sorted(said_sessions) or 'ничего'}")

# Every screenshot the README points at exists. A picture that does not open
# is a broken promise on the page that makes the first impression.
missing = [name for name in re.findall(r'src="(docs/screens/[^"]+)"', readme)
           if not os.path.exists(os.path.join(ROOT, name.replace("/", os.sep)))]
check("все снимки на месте", missing == [], f"| нет: {missing}")

# ---------------------------------------------------------------------------
# The documents somebody arriving meets first (`4.0b-C05`)
# ---------------------------------------------------------------------------
#
# A person who wants to help meets four things before they meet the code:
# how to contribute, how to behave, how to report, and the form that asks
# them what is needed. Missing any of them is not a gap in the docs — it is
# a person guessing, and then being told they guessed wrong.
print()
print("=== документы сообщества ===")

COMMUNITY = {
    "CONTRIBUTING.md": "как участвовать",
    "CODE_OF_CONDUCT.md": "как себя вести",
    "SECURITY.md": "куда нести уязвимость",
    os.path.join(".github", "ISSUE_TEMPLATE", "bug.yml"): "форма для поломки",
    os.path.join(".github", "ISSUE_TEMPLATE", "idea.yml"): "форма для идеи",
    os.path.join(".github", "PULL_REQUEST_TEMPLATE.md"): "форма для правки",
}
for name, what in COMMUNITY.items():
    check(f"есть {name} — {what}",
          os.path.exists(os.path.join(ROOT, name)))

contributing = io.open(os.path.join(ROOT, "CONTRIBUTING.md"),
                       encoding="utf-8").read()

# The licensing sentence has to match the decision, not the other way round.
# `ADR 0001` chose Apache-2.0 with no CLA; a CONTRIBUTING that asked for one
# would be asking for a signature nobody can accept.
check("вклад принимается без отдельного соглашения",
      "no CLA" in contributing or "нет CLA" in contributing,
      "| ADR 0001 выбрал Apache-2.0 без CLA")

# And the two things it tells a contributor to run must exist.
check("CONTRIBUTING называет действующий набор проверок",
      "tools/regress.py" in contributing
      and os.path.exists(os.path.join(ROOT, "tools", "regress.py")))
check("и действующий порождатель строк оболочки",
      "tools/gen_shell_strings.py" in contributing
      and os.path.exists(os.path.join(ROOT, "tools",
                                      "gen_shell_strings.py")))

# The habit this repository actually runs on. A CONTRIBUTING that left it
# out would be describing a different project: every check here has been
# broken on purpose at least once, and several were rewritten because of it.
check("и правило ломать собственную проверку",
      "break it" in contributing or "сломайте" in contributing.lower(),
      "| без него прочтут «напишите проверку» и напишут соглашающуюся")

# ---------------------------------------------------------------------------
# The promises made in public (`4.0b-C06`, `4.0b-C07`)
# ---------------------------------------------------------------------------
#
# Two of them, and both are the kind that is kept by being written down
# **before** there is any reason to break them.
#
# The one about money: said once, plainly, so that it cannot later read as a
# change of mind. The same sentence spoken after a paid plan appears is not
# the same sentence — the person chose without knowing.
#
# The one about incoming: a channel with no stated order of business is not
# a channel but a heap. Somebody who wrote on Monday and heard nothing by
# Wednesday should be able to look up whether that is normal.
print()
print("=== обещания, данные вслух ===")

product = io.open(os.path.join(ROOT, "PRODUCT.md"), encoding="utf-8").read()

check("README говорит, чего это стоит", "## What this costs" in readme,
      "| сказанное после появления платного читается как подмена")
check("и обещает, что локальная база останется бесплатной",
      "local base stays free" in readme)
check("и называет, что остаётся открытым",
      "What is open stays open" in readme)
check("то же обещание записано в PRODUCT.md",
      "Деньги — сказано один раз" in product)

# The promise names the class that keeps it. A promise pointing at code that
# does not exist is the shape this goes wrong in: the sentence survives a
# rename and stops being about anything.
check("обещание ссылается на существующий класс возможностей",
      "CommunityFeatures" in product
      and "class CommunityFeatures" in io.open(
          os.path.join(ROOT, "core", "features.py"),
          encoding="utf-8").read(),
      "| PRODUCT.md называет CommunityFeatures")

triage = os.path.join(ROOT, "docs", "TRIAGE.md")
check("есть порядок разбора входящего", os.path.exists(triage))
if os.path.exists(triage):
    order = io.open(triage, encoding="utf-8").read()
    # Four outcomes, and the fifth — silence — is the one it exists to
    # forbid. A document listing three of them leaves the fourth to chance.
    check("и он называет все четыре исхода",
          all(word in order for word in ("Берётся", "Уже есть",
                                         "Так задумано", "Не будет")),
          "| пятый исход — молчание — и есть то, что он запрещает")
    check("и обещает срок, а не «когда-нибудь»",
          "в течение недели" in order)
    check("README ведёт к нему", "docs/TRIAGE.md" in readme)

# ---------------------------------------------------------------------------
# The engines the README names, against the engines the settings offer
# ---------------------------------------------------------------------------
#
# The README listed five recognisers — «disabled, Google, Vosk, Whisper,
# PocketSphinx» — and the settings offer three. Google and PocketSphinx
# open a microphone of their own and were dropped in 4.0 (`4.0-E05`); the
# sentence stayed. The same sentence stood on the product page, and both
# were written from the same memory of the 3.1 list.
#
# The page is now checked (`tools/check_site.py`); this is the other half.
print()
print("=== движки в README против настроек ===")

sys.path.insert(0, ROOT)
import core.settings_schema as settings_schema

#: Engine key -> the word the README uses for it.
#:
#: The README writes for a developer and the settings for whoever is
#: choosing, so the words differ on purpose. A key missing from here is
#: reported as missing from here.
README_WORDS = {
    "silent": "silent",
    "pyttsx3": "pyttsx3",
    "edge": "Edge Neural TTS",
    "gtts": "gTTS",
    "piper": "Piper",
    "vosk": "Vosk",
    "whisper": "Whisper",
    "disabled": "disabled",
}

#: Setting -> what the report calls it, and the words its list sits between.
SPOKEN = {
    "tts_engine": ("речь", "**Text to speech:**", "."),
    "stt_engine": ("слух", "**Speech to text:**", "—"),
}

for key, (what, opens, closes) in SPOKEN.items():
    offered = [one["value"] for one in settings_schema.options_for(key, {})]
    unknown = [one for one in offered if one not in README_WORDS]
    check(f"{what}: у каждого движка есть слово для README", not unknown,
          f"| нет в таблице: {unknown} — допишите слово" if unknown else "")
    if unknown:
        continue
    line = next((one for one in readme.splitlines()
                 if one.strip().startswith(opens)), "")
    check(f"{what}: список в README на месте", bool(line),
          f"| строки, начинающейся с «{opens}», нет" if not line else "")
    if not line:
        continue
    # The parentheses go first, before anything else is done: in
    # "Edge Neural TTS (online, best quality)" the comma sits inside the
    # aside and tore the list apart, and the full stop in "(needs an
    # `.onnx` model)" cut it off halfway.
    plain = re.sub(r"\([^)]*\)", "", line.strip()[len(opens):])
    cut = plain.find(closes)
    if cut >= 0:
        plain = plain[:cut]
    # As sets: the order in the sentence is a matter of reading, the
    # membership is a matter of the settings.
    said = {one.strip().strip("`. ") for one in plain.split(",")
            if one.strip(". ")}
    want = {README_WORDS[one] for one in offered}
    check(f"{what}: те же движки, что в настройках", said == want,
          f"| README: {sorted(said)} | настройки: {sorted(want)}")

print()
print("ИТОГО ошибок:", fails)
sys.exit(1 if fails else 0)
