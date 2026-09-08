# -*- coding: utf-8 -*-
"""
S02: the threat model is checked against what is actually there.

Plan item `4.0-S02`. The acceptance criterion is written like this:
"every security requirement in this plan traces back to a point of the
model rather than to intuition". That is a checkable statement, and here it
is checked.

Prose cannot be checked as prose, and an attempt would be a deception. What
can be checked is three things that prose makes it especially easy to lie
about:

    1. **The named defence exists.** The plan item is in `ROADMAP.md`, the
       file is on disk. A model referring to a file that does not exist is
       a description of a program that does not exist.
    2. **The named proof runs.** The check exists, and the regression run
       finds it. A defence without a proof rests on nobody having touched
       it.
    3. **The reverse link.** Every security requirement in the plan traces
       back to at least one threat. That is the acceptance criterion
       itself: without it a defence can be added to the plan without
       answering "against what".

The list of requirements is kept here by hand — like `NEEDS` in
`check_surface_reachable.py`. It cannot be derived from the plan's text:
"security requirement" is a judgement, not a property of a line, and
automation would guess it from the words — that is, wrongly and silently.

To run:
    python tools/check_threat_model.py
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

MODEL = os.path.join("docs", "security", "THREAT-MODEL.md")
ROADMAP = os.path.join("docs", "ROADMAP.md")
STARTUP = os.path.join("shell", "Rina.Shell", "Startup.cs")

fails = 0


def check(label, ok, detail=""):
    global fails
    if not ok:
        fails += 1
    print(("OK   " if ok else "FAIL "), label, detail)


#: The plan's security requirements and the threats they trace back to.
#:
#: An item that gets in here must be named by at least one threat. An item
#: that is not here is either not about security or was forgotten: both are
#: worth turning the check red, because a silent "probably not about
#: security" is the very intuition the model was written to replace.
SECURITY_ITEMS = {
    "4.0-C04": "каталог разрешений",
    "4.0-C05": "контур подтверждения",
    "4.0-C06": "аудит вызовов",
    "4.0-D03": "рукопожатие: что сторона объявляет и чего не объявляет",
    "4.0-E06a": "предупреждение о нелокальном адресе модели",
    "4.0-F06": "глобальные сочетания и место под kill-switch",
    "4.0-F11": "диалог подтверждения",
    "4.0-G08": "политика источников индекса",
    "4.0-G09": "происхождение и доверие в записи индекса",
    "4.0-G10": "предупреждение о первом запуске недоверенного",
    "4.0-G11": "канонический путь и вычистка индекса",
    "4.0-G12": "запуски в журнале безопасности",
    "4.0-H04": "установка плагина из папки или архива",
    "4.0-H06": "границы плагинов",
    "4.0-H07": "плагин в отдельном процессе",
    "4.0-I03": "диагностический пакет",
    "4.0-U04": "скачивание и целостность",
    "4.0b-A03": "наблюдение за тем, какие программы открыты",
    "4.0b-C02a": "разбор ввозимого файла команд",
}

text = io.open(MODEL, encoding="utf-8").read()
roadmap = io.open(ROADMAP, encoding="utf-8").read()

#: A threat and the "Чем:" line under it.
#:
#: The format is deliberately simple: a heading `### T-NN · name`, and
#: then somewhere before the next heading a line beginning with `Чем:`.
#: Parsing the prose more finely would mean introducing a second
#: description language beside the first.
threats = {}
current = None
for line in text.split("\n"):
    head = re.match(r"### (T-\d+) · (.+)", line.strip())
    if head:
        current = head.group(1)
        threats[current] = {"name": head.group(2), "why": "", "rest": False}
        continue
    if current is None:
        continue
    if line.startswith("Чем:"):
        threats[current]["why"] = line[len("Чем:"):].strip()
    elif line.startswith("Чем: ") or line.strip().startswith("Чем: "):
        threats[current]["why"] = line.split("Чем:", 1)[1].strip()
    if line.startswith("Остаток"):
        threats[current]["rest"] = True

print("=== модель прочитана ===")
check("угрозы найдены", len(threats) >= 10, f"| {len(threats)}")
check("нумерация без дыр",
      sorted(threats) == [f"T-{i:02d}" for i in range(1, len(threats) + 1)],
      f"| {sorted(threats)}")

print()
print("=== у каждой угрозы есть защита и назван остаток ===")

for tid in sorted(threats):
    threat = threats[tid]
    check(f"{tid} — чем защищаем сказано", bool(threat["why"]),
          f"| {threat['name']}")
    # The residue is always named: "there is no residue" is a line too,
    # and it has to be written. Silence would mean nobody thought about
    # it.
    check(f"{tid} — остаток назван", threat["rest"], f"| {threat['name']}")

print()
print("=== названная защита существует ===")

# Everything the model refers to: plan items, files, shell modes.
named_items, named_files, named_modes = set(), set(), set()
for threat in threats.values():
    for token in re.findall(r"`([^`]+)`", threat["why"]):
        # `4.0b-` as well: a defence added during the beta is as much a
        # security requirement as any other, and is obliged to trace back
        # to the model on the same terms. Without that letter such an item
        # would drop out of the check in both directions silently — that
        # is, it would look linked without being linked.
        if re.fullmatch(r"4\.0b?-[A-Z]\d+[a-z]?", token):
            named_items.add(token)
        elif token.startswith("--check-"):
            named_modes.add(token)
        elif "/" in token:
            named_files.add(token)

for item in sorted(named_items):
    check(f"пункт {item} есть в плане", f"**{item}" in roadmap)

for path in sorted(named_files):
    check(f"файл {path} на месте", os.path.isfile(path))

print()
print("=== названное доказательство запускается ===")

# The regression run derives its list itself: `tools/test_*.py`,
# `tools/check_*.py` and the `--check-*` modes the shell declares. So it is
# enough to check that the named proof falls under that rule — then it is
# run by the regression rather than lying next to it.
startup = io.open(STARTUP, encoding="utf-8").read()
declared_modes = set(re.findall(r'"(--check-[a-z]+)"', startup))

for path in sorted(named_files):
    if not path.startswith("tools/"):
        continue
    name = os.path.basename(path)
    check(f"проверка {name} попадает в регресс",
          name.startswith(("test_", "check_")),
          "| регресс берёт только test_* и check_*")

for mode in sorted(named_modes):
    check(f"режим {mode} объявлен оболочкой", mode in declared_modes,
          f"| {sorted(declared_modes)}")

print()
print("=== требования плана возводятся к модели ===")

# That reverse link. Without it the model is an essay: it describes the
# defences its author remembered and says nothing about the ones they
# forgot.
for item, what in sorted(SECURITY_ITEMS.items()):
    check(f"{item} ({what}) возводится к угрозе", item in named_items,
          "| требование безопасности, не названное ни одной угрозой")

# And the other way round: an item named by the model but not recognised
# as a security requirement is a discrepancy of the same kind.
for item in sorted(named_items):
    check(f"{item} назван требованием безопасности", item in SECURITY_ITEMS,
          "| модель ссылается на него, а список требований о нём не знает")

print()
print("=== модель названа там, где её будут искать ===")

check("проверка названа в самой модели",
      "check_threat_model.py" in text)
check("модель названа в плане", "THREAT-MODEL" in roadmap,
      "| иначе её найдёт только тот, кто уже знает о ней")

print()
print("ИТОГО ошибок:", fails)
sys.exit(1 if fails else 0)
