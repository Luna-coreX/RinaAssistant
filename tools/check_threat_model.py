# -*- coding: utf-8 -*-
"""
S02: модель угроз сверяется с тем, что есть на самом деле.

Задача плана `4.0-S02`. Критерий приёмки записан так: «каждое требование
безопасности в этом плане возводится к пункту модели, а не к интуиции». Это
проверяемое утверждение, и здесь оно проверяется.

Документ прозой проверить нельзя, и попытка была бы обманом. Зато можно
проверить три вещи, соврать в которых прозой особенно легко:

    1. **Названная защита существует.** Пункт плана есть в `ROADMAP.md`,
       файл есть на диске. Модель, ссылающаяся на несуществующий файл, —
       описание программы, которой нет.
    2. **Названное доказательство запускается.** Проверка есть, и регресс
       её находит. Защита без доказательства держится на том, что её никто
       не трогал.
    3. **Обратная связь.** Каждое требование безопасности из плана
       возводится хотя бы к одной угрозе. Это и есть критерий приёмки:
       без него в план можно добавить защиту, не ответив «от чего».

Список требований ведётся здесь руками — как `NEEDS` в
`check_surface_reachable.py`. Выводить его из текста плана нельзя:
«требование безопасности» — суждение, а не признак строки, и автоматика
угадывала бы его по словам, то есть неверно и молча.

Запуск:
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


#: Требования безопасности плана и угрозы, к которым они возводятся.
#:
#: Пункт, попавший сюда, обязан быть назван хотя бы в одной угрозе. Пункт,
#: которого здесь нет, — это либо не про безопасность, либо забытый: и то и
#: другое стоит того, чтобы проверка покраснела, потому что молчаливое
#: «наверное, не про безопасность» и есть та самая интуиция, вместо которой
#: писалась модель.
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
}

text = io.open(MODEL, encoding="utf-8").read()
roadmap = io.open(ROADMAP, encoding="utf-8").read()

#: Угроза и строка «Чем:» под ней.
#:
#: Формат нарочно простой: заголовок `### T-NN · имя`, а дальше где-то до
#: следующего заголовка — строка, начинающаяся с `Чем:`. Разбирать прозу
#: тоньше — значит завести второй язык описания рядом с первым.
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
    # Остаток называется всегда: строка «остатка нет» тоже строка, и её
    # приходится написать. Молчание значило бы, что о нём не подумали.
    check(f"{tid} — остаток назван", threat["rest"], f"| {threat['name']}")

print()
print("=== названная защита существует ===")

# Всё, на что модель ссылается: пункты плана, файлы, режимы оболочки.
named_items, named_files, named_modes = set(), set(), set()
for threat in threats.values():
    for token in re.findall(r"`([^`]+)`", threat["why"]):
        if re.fullmatch(r"4\.0-[A-Z]\d+[a-z]?", token):
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

# Регресс выводит список сам: `tools/test_*.py`, `tools/check_*.py` и
# режимы `--check-*`, объявленные оболочкой. Значит достаточно проверить,
# что названное доказательство попадает под это правило, — тогда оно
# запускается регрессом, а не лежит рядом с ним.
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

# Та самая обратная связь. Без неё модель — сочинение: она описывает те
# защиты, которые автор вспомнил, и молчит о тех, которые забыл.
for item, what in sorted(SECURITY_ITEMS.items()):
    check(f"{item} ({what}) возводится к угрозе", item in named_items,
          "| требование безопасности, не названное ни одной угрозой")

# И в обратную сторону: пункт, названный моделью, но не признанный
# требованием безопасности, — расхождение того же рода.
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
