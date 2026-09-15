# -*- coding: utf-8 -*-
"""
4.0b-C01: the security sweep — **by the threat model, not from memory**.

Every threat in [THREAT-MODEL.md](../docs/security/THREAT-MODEL.md) either has
an executable assertion here or is named below as covered elsewhere, with the
check that covers it. The list of threats is **read out of the document**, so
a threat added to the model and forgotten here turns this red.

**Why that last part is the whole point.** A security sweep written as a list
of things somebody thought of is a sweep of what somebody thought of. The
model is the place where threats are enumerated and argued; if the sweep does
not take its list from there, the two go out of step in the direction that
always loses — the document grows and the checks do not.

**And why the sweep exists at all when the individual checks already pass.**
Each of them was written next to the thing it guards, by somebody thinking
about that thing. This one is read in one sitting, against the document, by
somebody asking whether the promises still hold. Those are different
readings, and the second one is what a release needs.
"""
import io
import os
import re
import sys

sys.path.insert(0, r"C:\DevStation\PCDev\DesktopApps\RinaAssistant")
sys.path.insert(0, os.path.join(
    r"C:\DevStation\PCDev\DesktopApps\RinaAssistant", "tools"))

from console import use_utf8

use_utf8()

ROOT = r"C:\DevStation\PCDev\DesktopApps\RinaAssistant"
MODEL = os.path.join(ROOT, "docs", "security", "THREAT-MODEL.md")

fails = 0
#: Which threats this file actually exercises. Filled by `about`.
covered = set()


def check(label, cond, detail=""):
    global fails
    if not cond:
        fails += 1
    print(("OK   " if cond else "FAIL "), label, detail)


def about(threat, label, cond, detail=""):
    """An assertion attributed to a threat of the model."""
    covered.add(threat)
    check(f"{threat} · {label}", cond, detail)


#: Threats not exercised here, and what does exercise them.
#:
#: A list of exceptions is a place where things go to be forgotten, so each
#: entry says **where** it is covered instead — and the coverage check below
#: insists that place exists. "Covered elsewhere" without a named elsewhere
#: is the same as not covered.
ELSEWHERE = {
    "T-01": "--check-platform · подмена по имени, индекс оболочки",
    "T-02": "--check-platform · канонический путь цели ярлыка",
    "T-03": "--check-platform · подпись и окно доверия",
    "T-04": "--check-platform · вычистка индекса",
    "T-05": "--check-platform · журнал безопасности запусков",
    "T-08": "tools/test_plugins.py · срок на вызов, сосед цел",
    "T-09": "tools/test_plugins.py · замена выключает плагин",
    "T-11": "поверхность 5.0 — управления компьютером в 4.0 нет",
    "T-12": "поверхность 5.0 — там же",
    "T-14": "--check-updates · подпись и целостность обновления",
    "T-15": "--check-diagnostics · состав диагностического пакета",
}


# ===========================================================================
# Surface 1 — launching programs
# ===========================================================================
from core import data_transfer

# T-18 · an imported command launches the wrong thing.
imported = data_transfer.commands_from_data({
    "kind": data_transfer.KIND_COMMANDS,
    "format": data_transfer.FORMAT_VERSION,
    "payload": {"commands": [
        {"type": "system", "target": "shutdown", "triggers": ["привет"]},
        {"type": "неизвестно", "target": r"C:\Windows\System32\calc.exe",
         "triggers": ["считалка"]},
    ]},
})
about("T-18", "ввезённое приезжает выключенным",
      all(not c.get("enabled") for c in imported),
      f"| {[c.get('enabled') for c in imported]}")
about("T-18", "самодельное системное действие не проезжает",
      not any(c.get("type") == "system" and c.get("target") == "shutdown"
              for c in imported),
      f"| {[(c.get('type'), c.get('target')) for c in imported]}")
about("T-18", "незнакомый вид перестаёт что-либо запускать",
      all(c.get("type") != "неизвестно" for c in imported),
      f"| {[c.get('type') for c in imported]}")

# T-21 · a trial runs a card rather than a reference to one.
huge = data_transfer.sanitize_command({
    "type": "sequence", "triggers": [],
    "steps": [{"type": "website", "target": f"{n}.example"}
              for n in range(300)],
})
about("T-21", "карточка ограничена по числу шагов",
      len(huge["steps"]) == 50, f"| шагов {len(huge['steps'])}")
about("T-21", "и по длине цели",
      len(data_transfer.sanitize_command(
          {"type": "speak", "target": "щ" * 5000})["target"]) <= 1000)


# ===========================================================================
# Surface 2 — plugins
# ===========================================================================
from core import permissions
from plugins import manager

# T-07 · a plugin asks for a dangerous permission.
allowed, denied = permissions.plugin_allowed(
    ["system.power", "files.write", "network.external"])
about("T-07", "опасное разрешение плагину не выдаётся",
      "system.power" in denied and "files.write" in denied,
      f"| отказано {denied}")
about("T-07", "а обычное — выдаётся",
      allowed == ["network.external"], f"| разрешено {allowed}")
about("T-07", "выдуманное разрешение тоже отказано",
      "чего.нибудь" in permissions.plugin_allowed(["чего.нибудь"])[1])

# T-06 · the reserved permissions are on no tool at all. The model says this
# as a statement, not an observation, so it is checked as one.
from core.toolbox import ALL_TOOLS

on_tools = set()
for tool in ALL_TOOLS:
    on_tools |= set(tool.permissions)
about("T-06", "зарезервированное не выдано ни одному инструменту",
      not (on_tools & permissions.RESERVED),
      f"| пересечение {sorted(on_tools & permissions.RESERVED)}")

# T-10 · a plugin's name used as a path.
#
# The model promises two things, and the second is the one that matters: the
# name is checked by a pattern, and **the resulting path** is checked
# separately — it has to land directly inside the plugins directory.
#
# The first version of this check demanded that "a/b" be refused. It is not
# refused: separators are replaced before the pattern is applied, so it
# becomes "a_b" — just as safe, and not what the model claims. The assertion
# had misread the design and would have gone on demanding the wrong
# behaviour of it.
hostile = ["../../etc", "..", ".", "", "../plugins/other", "  "]
slipped = []
for raw in hostile:
    try:
        manager._safe_plugin_id(raw)
        slipped.append(raw)
    except Exception:
        pass
about("T-10", "имя, ведущее наружу, отвергается", slipped == [],
      f"| прошло {slipped}")

# And whatever a name does become, it stays inside the directory. Asserted
# over the produced path, because that is what the model promises and what
# somebody planting an archive actually cares about.
base = os.path.abspath(manager.plugins_dir())
escaped = []
for raw in ["a/b", "a" + chr(92) + "b", "/", "лишь.бы.что", "a" * 200,
            "x..y", "..a", "a.."]:
    try:
        made = manager._safe_plugin_id(raw)
    except Exception:
        continue
    where = os.path.abspath(os.path.join(base, made))
    if os.path.dirname(where) != base or where == base:
        escaped.append((raw, where))
about("T-10", "получившийся путь остаётся внутри каталога плагинов",
      escaped == [], f"| вышло наружу {escaped}")


# T-22 · a scenario looks at what a person is busy with.
#
# The same information as `T-19` — what is open — but reached by a question
# from inside a command the person wrote, not by a subscription. What must
# hold is that nothing is kept, and that no answer means no.
from voice.user_commands import _condition_holds

seen_questions = []


def watcher(question, about=""):
    seen_questions.append((question, about))
    return "C:/Apps/Chrome/chrome.exe"


held = _condition_holds("app_active", "chrome", "",
                        {"vars": {}, "machine": watcher})
about("T-22", "условие спрашивает у оболочки и получает ответ", held,
      f"| {seen_questions}")

# Nothing is kept: the state a run carries holds variables and nothing
# about the machine. Asserted over what the run actually carries, because
# "we do not store it" is the whole promise.
carried = {"vars": {}, "machine": watcher}
_condition_holds("app_active", "chrome", "", carried)
_condition_holds("app_running", "chrome", "", carried)
leftovers = [key for key, value in carried.items()
             if key != "machine" and "chrome" in str(value).lower()]
about("T-22", "об открытой программе ничего не оседает", leftovers == [],
      f"| осело в {leftovers}")

about("T-22", "без оболочки условие о машине ложно",
      not _condition_holds("app_running", "chrome", "", {"vars": {}}))


# ===========================================================================
# Surface 4 — cloud connectors
# ===========================================================================
from core import settings_schema

ok_local, code_local, _ = settings_schema.validate(
    "llm_url", "http://localhost:11434")
ok_far, code_far, said_far = settings_schema.validate(
    "llm_url", "http://example.com:11434")

# T-13 · the conversation leaves for somebody else's machine.
about("T-13", "локальный адрес принимается молча",
      ok_local and not code_local, f"| {code_local}")
about("T-13", "нелокальный принимается, но с предупреждением",
      ok_far and code_far == "llm.remote_address" and said_far,
      f"| {code_far}: {said_far[:60] if said_far else ''}")
about("T-13", "по умолчанию адрес локальный",
      "localhost" in str(settings_schema.DEFAULTS.get("llm_url", "")),
      f"| {settings_schema.DEFAULTS.get('llm_url')}")


# ===========================================================================
# Surface 5 — watching what is open
# ===========================================================================
from core.engine import RinaEngine
from core.settings_api import MemorySettings

watching = MemorySettings({
    "custom_commands": [], "history": [], "reminders": [], "todo": [],
})
engine = RinaEngine(settings=watching)

# T-19 · Rina remembers what a person is busy with.
about("T-19", "наблюдение выключено по умолчанию",
      settings_schema.DEFAULTS.get("watch_apps") in (False, None, [], ""),
      f"| {settings_schema.DEFAULTS.get('watch_apps')}")

engine.note_foreground(r"C:\Apps\Secret\diary.exe")
engine.note_foreground(r"C:\Apps\Other\thing.exe")
kept = {key: watching.get(key) for key in watching.all()}
trace = [key for key, value in kept.items()
         if "diary" in str(value) or "Secret" in str(value)]
about("T-19", "о том, что было открыто, не остаётся следа",
      trace == [], f"| осело в {trace}")


# ===========================================================================
# Surface 6 — installing packages
# ===========================================================================
from core import models

# T-20 · the installation brings the wrong code.
#
# Written as an equality on purpose: the list of what Rina may install on
# somebody's machine grows only deliberately, and a check that merely
# counted them would let a name in quietly. When this goes red, the
# question is not "update the check" but "was this package meant to be
# here" — and then both lines change together.
named_packages = {p.pip for p in models.PACKAGES}
about("T-20", "устанавливаемое перечислено таблицей ядра",
      named_packages == {"vosk", "faster-whisper", "piper-tts", "edge-tts"},
      f"| {sorted(named_packages)}")

# And each name is a name. `pip install` takes a URL, a path, a local
# archive and options in the same argument it takes a package name in, so
# "the list is in code" is only half the promise: an entry reading
# `--index-url http://…` would be in the table and would still bring the
# wrong code.
import re as _re

ILL_NAMED = [p.pip for p in models.PACKAGES
             if not _re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?",
                                  p.pip)]
about("T-20", "и каждое имя — имя, а не ссылка, путь или ключ",
      not ILL_NAMED, f"| {ILL_NAMED}")

# That an identifier arriving from outside cannot become a package name is
# checked end to end in its own file; the sweep says where, and insists the
# file is there.
about("T-20", "имя берётся из таблицы, а не из запроса — tools/test_packages.py",
      os.path.exists(os.path.join(ROOT, "tools", "test_packages.py")))


# ===========================================================================
# Across everything
# ===========================================================================
from core.audit import redact_args
from core.confirmations import ConfirmationError, ConfirmationLedger
from core.toolbox import POWER_ACTION

# T-16 · the journal gives away the content of the conversation.
said = redact_args(None, {"query": "как лечить то, о чём я не говорю вслух"})
about("T-16", "свободный текст в журнал не попадает",
      "лечить" not in str(said), f"| {said}")
about("T-16", "но длина остаётся — пустой ввод отличим от длинного",
      "симв" in str(said.get("query", "")), f"| {said}")

kept_verbatim = redact_args(None, {"query": "секрет"}, verbatim=True)
about("T-16", "дословно — только по явно включённой настройке",
      kept_verbatim.get("query") == "секрет", f"| {kept_verbatim}")

# T-17 · a dangerous action from a misheard phrase.
ledger = ConfirmationLedger()
granted = ledger.issue("power_action", {"action": "sleep"})
try:
    ledger.redeem(granted.id, "power_action", {"action": "shutdown"})
    swapped = True
except ConfirmationError:
    swapped = False
about("T-17", "согласие на «усыпить» не годится для «выключить»",
      not swapped)

again = ConfirmationLedger()
one = again.issue("power_action", {"action": "sleep"})
again.redeem(one.id, "power_action", {"action": "sleep"})
try:
    again.redeem(one.id, "power_action", {"action": "sleep"})
    reused = True
except ConfirmationError:
    reused = False
about("T-17", "предъявление однократно", not reused)

about("T-17", "необратимое объявлено требующим подтверждения",
      POWER_ACTION.confirm_required)


# ===========================================================================
# The public statement of the boundary (`4.0b-C03`)
# ===========================================================================
#
# `SECURITY.md` is what somebody outside reads before deciding how much to
# trust this program. Prose cannot be checked, but the **values it quotes**
# can — and quoting a value is exactly how a document goes quietly out of
# date: the code moves, the sentence stays, and the sentence is the part the
# reader believes.
#
# This item exists because that already happened: the file said "there is no
# sandbox" long after plugins had moved into processes of their own. That
# particular sentence cannot be caught by a check; the numbers and labels
# around it can be, and those are what drift next.
import json

policy = io.open(os.path.join(ROOT, "SECURITY.md"), encoding="utf-8").read()
strings = json.load(io.open(
    os.path.join(ROOT, "shell", "Rina.Shell", "Strings", "interface.json"),
    encoding="utf-8"))


def in_english(key):
    return (strings.get(key) or {}).get("English", key)


check("SECURITY.md называет действующий адрес модели по умолчанию",
      str(settings_schema.DEFAULTS.get("llm_url", "")) in policy,
      f"| {settings_schema.DEFAULTS.get('llm_url')}")

from core.logging_setup import logs_dir

tail = os.path.basename(os.path.dirname(logs_dir())) + "/" +     os.path.basename(logs_dir())
check("и действующее место журналов", tail in policy.replace("\\", "/"),
      f"| {tail}")

# The setting is named by its English label and by the section it is in.
# Both move: the label was reworded once already, and `log_texts` sits under
# Privacy, not under Diagnostics as the file used to say.
label = in_english("Записывать тексты реплик")
check("и действующее название настройки текстов", label in policy,
      f"| «{label}»")

layout = io.open(os.path.join(ROOT, "shell", "Rina.Shell", "Pages",
                              "SettingsLayout.cs"), encoding="utf-8").read()
before = layout[:layout.index('new("log_texts"')]
section = re.findall(r'new\(Word\("([^"]+)"\)', before)[-1]
# The whole phrase, not the bare word. "Privacy" appears twice in the file
# for unrelated reasons, so asking whether it occurs at all answered yes
# while the sentence said "Settings → Diagnostics" — the very drift this is
# here to catch. Found by breaking it: the check stayed green.
pointer = f"Settings → {in_english(section)}"
check("и раздел настроек, в котором она лежит", pointer in policy,
      f"| ждали «{pointer}»")


# ===========================================================================
# The sweep is only as good as its list of threats
# ===========================================================================
#
# Read out of the document. A threat added to the model and forgotten here
# has to turn this red — otherwise the sweep quietly becomes a sweep of what
# somebody once thought of.
text = io.open(MODEL, encoding="utf-8").read()
named = set(re.findall(r"^### (T-\d+)", text, re.MULTILINE))
check("угрозы в модели вообще нашлись", len(named) >= 15,
      f"| {len(named)}")

forgotten = sorted(named - covered - set(ELSEWHERE))
check("каждая угроза модели либо проверена здесь, либо названа",
      forgotten == [],
      f"| без проверки: {forgotten}" if forgotten else f"| угроз {len(named)}")

# And the other way: an entry here about a threat the model no longer has is
# a check guarding something nobody is afraid of any more.
stale = sorted((covered | set(ELSEWHERE)) - named)
check("здесь нет угроз, которых нет в модели", stale == [],
      f"| лишние: {stale}")

# A deferral has to name a real place. "Covered elsewhere" pointing at a
# check that does not exist is worse than no deferral: it reads as coverage.
missing = []
for threat, where in ELSEWHERE.items():
    if where.startswith("tools/"):
        if not os.path.exists(os.path.join(ROOT, where.split(" ")[0])):
            missing.append(threat)
    elif where.startswith("--check-"):
        flag = where.split(" ")[0]
        startup = io.open(os.path.join(ROOT, "shell", "Rina.Shell",
                                       "Startup.cs"), encoding="utf-8").read()
        if f'"{flag}"' not in startup:
            missing.append(threat)
check("отложенное указывает на существующую проверку", missing == [],
      f"| не нашлось: {missing}")

print()
print("ИТОГО ошибок:", fails)
sys.exit(1 if fails else 0)
