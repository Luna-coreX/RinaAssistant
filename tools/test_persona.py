# -*- coding: utf-8 -*-
"""
The persona: what the model is actually told (`4.0b-E14`).

Checked where it lands rather than where it is written: through the real
`llm.ask`, with only the network call replaced, reading the system prompt
the model receives. A persona can be right in the source and wrong on
arrival — this one was: every line correct in the editor, and the model
got «…ассистент Luna.Общайся тепло…», because Python joins adjacent
literals without a space and says nothing.

Four things, each found or decided while making the persona translatable:

**The name is one paragraph, and without it nothing is left dangling.**
Empty is the ordinary case, not an error. A name written into the text
would leave «если  расстроен» when there is none — and would have to
decline when there is one, which no template does for an arbitrary name.

**The persona follows the language.** A Russian instruction was found to
take every other language away from the model: spoken to in English, it
stopped answering. In an English window the model must be told in English.

**A persona of the person's own still gets the name.** The name is a
setting of its own; giving it should not depend on which character was
picked.

**The name is on the privacy page.** It is personal data, and the page
that promises to list everything must list it — by construction, because
it is an ordinary setting, and checked here because E14 is where it began.

To run:
    python tools/test_persona.py
"""
import os
import re
import sys

sys.path.insert(0, r"C:\DevStation\PCDev\DesktopApps\RinaAssistant")
sys.path.insert(0, os.path.join(
    r"C:\DevStation\PCDev\DesktopApps\RinaAssistant", "tools"))

from sandbox import neutralise

# The real `ask` is kept before the sandbox replaces it: this check is
# about what `ask` sends, so it substitutes the layer below instead — the
# one call that would reach the model.
from core import llm as _llm

_real_ask = _llm.ask
neutralise(storage=False)
_llm.ask = _real_ask

from console import use_utf8
from core import i18n, llm, privacy
from core.settings_api import MemorySettings

use_utf8()

fails = 0


def check(label, cond, detail=""):
    global fails
    if not cond:
        fails += 1
    print(("OK   " if cond else "FAIL "), label, detail)


def told(**settings):
    """The system prompt the model receives, with these settings."""
    asked = []

    def model(path, payload=None, timeout=None):
        system = [m for m in payload["messages"] if m["role"] == "system"]
        asked.append(system[0]["content"] if system else "")
        return {"message": {"content": "…"}}

    values = {"llm_enabled": True, "llm_web": False, "llm_model": "m",
              "llm_timeout": 30}
    values.update(settings)
    was_request, was_settings = llm._request, llm._settings
    llm._request = model
    llm._settings = lambda: MemorySettings(values)
    try:
        llm.ask("привет")
    finally:
        llm._request, llm._settings = was_request, was_settings
    return asked[0] if asked else ""


#: A sentence ending straight into a letter: the shape the glued persona
#: had. Checked on the text the model gets, because the source check
#: (`check_glued.py`) sees literals and this is what they turned into.
GLUED = re.compile(r"[.,;:!?…»][A-Za-zА-Яа-яЁё]")
CYRILLIC = re.compile(r"[А-Яа-яЁё]")

i18n.set_language("Русский")

print("=== без имени ===")
bare = told()
check("имени нет — нет и абзаца про него",
      "зовут" not in bare, "| абзац с пустым именем остался")
check("и подстановка не торчит наружу",
      "{name}" not in bare and "{" not in bare, "| в тексте фигурная скобка")
check("пробелы не сдвоены там, где было имя",
      "  " not in bare, "| двойной пробел — след выпавшего слова")
check("склеек нет", not GLUED.search(bare),
      f"| {GLUED.search(bare).group(0) if GLUED.search(bare) else ''}")
check("персона на месте", bare.startswith("Ты — Рина"),
      f"| {bare.splitlines()[0]}")

print()
print("=== с именем ===")
named = told(user_name="Саша")
check("имя названо", "зовут Саша." in named, "| абзаца с именем нет")
check("и ровно один раз", named.count("Саша") == 1,
      f"| {named.count('Саша')} раз — имя просочилось в другие абзацы")
check("остальное то же самое",
      named.replace(llm.NAMED.format(name="Саша") + "\n", "") == bare,
      "| без абзаца с именем текст отличается от безымянного")
check("склеек нет и тут", not GLUED.search(named))

# A line break typed into the name field would split the prompt where
# nobody meant a paragraph; the whitespace is collapsed on the way in.
broken = told(user_name="Са\nша")
check("перевод строки в имени не рвёт текст",
      broken.count("\n") == named.count("\n"),
      f"| строк {broken.count(chr(10))} против {named.count(chr(10))}")

print()
print("=== по-английски ===")
i18n.set_language("English")
try:
    english = told(user_name="Sasha")
    stray = CYRILLIC.findall(english)
    check("персона целиком английская", not stray,
          f"| кириллицы: {len(stray)} букв, начало: "
          f"{english[english.find(stray[0]) - 20:][:60] if stray else ''}")
    check("и имя в ней", "name is Sasha." in english,
          f"| {english.splitlines()[0]}")
    check("склеек нет и тут", not GLUED.search(english))
finally:
    i18n.set_language("Русский")

print()
print("=== свой характер ===")
own = told(llm_persona="Отвечай как пират.")
check("свой характер заменяет персону целиком",
      own == "Отвечай как пират.", f"| {own!r}")
own_named = told(llm_persona="Отвечай как пират.", user_name="Саша")
check("а имя к нему добавляется",
      own_named.startswith("Отвечай как пират.\n")
      and "зовут Саша." in own_named, f"| {own_named[:80]!r}")

print()
print("=== имя на странице приватности ===")
store = MemorySettings({"user_name": "Саша"})
kept = {item["id"]: item["detail"]
        for group in privacy.inventory(store) if group["id"] == "settings"
        for item in group["items"]}
check("заданное имя видно среди того, что о человеке известно",
      kept.get("user_name") == "Саша", f"| {kept.get('user_name')!r}")

print()
print("ИТОГО ошибок:", fails)
sys.exit(1 if fails else 0)
