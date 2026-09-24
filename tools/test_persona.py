# -*- coding: utf-8 -*-
"""
The persona: what the model is actually told (`4.0b-E14`).

Checked where it lands rather than where it is written: through the real
`llm.ask`, with only the network call replaced, reading the system prompt
the model receives. A persona can be right in the source and wrong on
arrival — this one was: every line correct in the editor, and the model
got «…ассистент Luna.Общайся тепло…», because Python joins adjacent
literals without a space and says nothing.

The prompt is a character and a situation. The character is one of the
ready ones, chosen in the settings, or one of the person's own; the
situation is what is true whatever the character — and each part of it
was found or decided here:

**The name is one paragraph, and without it nothing is left dangling.**
Empty is the ordinary case, not an error. A name written into the text
would leave «если  расстроен» when there is none — and would have to
decline when there is one, which no template does for an arbitrary name.

**The gender is said, not guessed.** Neutral wording in the persona does
not settle it: the model picks «ты прав» or «ты права» in its reply, and a
model told nothing picks the masculine for everybody. So the persona never
says «он» about the person, and the address form says the rest.

**"Spoken aloud" only when it will be.** Said always, it was false with
the voice off; said never, a list got read aloud. And markup never: the
window does not render it either.

**The persona follows the language.** A Russian instruction was found to
take every other language away from the model: spoken to in English, it
stopped answering. In an English window the model must be told in English.

**The name and the form are on the privacy page.** Personal data, and the
page that promises to list everything must list them — by construction,
because they are ordinary settings, and checked here because this is
where they began.

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
from core import i18n, llm, privacy, settings_schema
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
#: A masculine pronoun. In the character's paragraphs there is nothing
#: male for one to refer to but the person — so any of these decides the
#: person's gender for everybody who reads the persona, and a use that
#: means something else is worth rephrasing anyway.
HE = re.compile(r"\b(?:он|его|ему|им|ним|него|нему|нём)\b", re.I)

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
print("=== род ===")
pronouns = sorted({m.group(0) for persona in llm.PERSONAS.values()
                   for p in persona for m in HE.finditer(p)})
check("характер не говорит о человеке «он»", not pronouns,
      f"| {', '.join(pronouns)}")
check("по умолчанию — без рода, и это сказано модели",
      llm.ADDRESS["neutral"] in bare, "| модели не сказано, что род неизвестен")
for form in ("masculine", "feminine"):
    chosen = told(address_form=form)
    others = [f for f in llm.ADDRESS if f != form and llm.ADDRESS[f] in chosen]
    check(f"{form}: сказано именно это",
          llm.ADDRESS[form] in chosen and not others,
          f"| прочие формы в тексте: {others}")
check("незнакомое значение — как без рода",
      llm.ADDRESS["neutral"] in told(address_form="мусор"))

print()
print("=== вслух ===")
aloud = told(tts_engine="edge", voice_reply=True)
check("голос включён — сказано, что ответ прозвучит",
      llm.SPOKEN in aloud, "| про голос ни слова")
check("движок «без озвучки» — не сказано, и слова «вслух» нет вовсе",
      "вслух" not in bare, "| текст обещает голос, которого нет")
check("ответ голосом выключен — не сказано",
      llm.SPOKEN not in told(tts_engine="edge", voice_reply=False))
check("без разметки — всегда",
      llm.PLAIN in bare and llm.PLAIN in aloud, "| про разметку не сказано")

print()
print("=== по-английски ===")
i18n.set_language("English")
try:
    # Everything the situation can add, at once: a Russian line anywhere
    # in it pulls the answer into Russian as surely as the character does.
    english = told(user_name="Sasha", address_form="feminine",
                   tts_engine="edge")
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
print("=== предлагается только то, что знает персону ===")
# The reason Ukrainian, Spanish and German were withdrawn, turned into the
# rule for bringing one back: a language is offered only when all of the
# persona and everything the situation adds is translated into it. A
# language added to `LANGUAGES` with its persona in Russian would be the
# finding this began with, promised in the settings.
every = [*(p for persona in llm.PERSONAS.values() for p in persona),
         llm.NAMED, llm.PLAIN, llm.SPOKEN, *llm.ADDRESS.values()]
for lang in i18n.LANGUAGES:
    if lang == "Русский":
        continue
    table = i18n._TRANSLATIONS.get(lang) or {}
    missing = [p for p in every if p not in table]
    check(f"{lang}: персона переведена целиком", not missing,
          f"| без перевода {len(missing)} из {len(every)}")

print()
print("=== выбор характера ===")
default = next(iter(llm.PERSONAS))
check("по умолчанию — тёплая", default == "warm" and bare.startswith(llm.WARM[0]),
      f"| по умолчанию {default!r}: {bare.splitlines()[0]}")
brief = told(llm_character="brief")
check("сдержанная выбирается",
      brief.startswith(llm.BRIEF[0]) and llm.WARM[1] not in brief,
      f"| {brief.splitlines()[0]}")
check("и положение дел к ней добавляется так же",
      llm.ADDRESS["neutral"] in brief and llm.PLAIN in brief,
      "| сдержанная осталась без рода и разметки")
check("незнакомый характер — как по умолчанию",
      told(llm_character="мусор") == bare)
offered = settings_schema.options_for("llm_character", {})
check("настройки предлагают все характеры, и у каждого есть слово",
      [o["value"] for o in offered] == list(llm.PERSONAS)
      and all(o["title"] for o in offered),
      f"| {[(o['value'], o['title']) for o in offered]}")

print()
print("=== свой характер ===")
own = told(llm_persona="Отвечай как пират.")
check("свой характер заменяет персону целиком",
      own.startswith("Отвечай как пират.\n") and "Ты — Рина" not in own,
      f"| {own[:60]!r}")
check("свой характер важнее выбранного",
      llm.BRIEF[0] not in told(llm_persona="Отвечай как пират.",
                                llm_character="brief"))
own_named = told(llm_persona="Отвечай как пират.", user_name="Саша",
                 address_form="feminine", tts_engine="edge")
check("а положение дел к нему добавляется",
      "зовут Саша." in own_named and llm.ADDRESS["feminine"] in own_named
      and llm.SPOKEN in own_named, f"| {own_named[:80]!r}")

print()
print("=== на странице приватности ===")
store = MemorySettings({"user_name": "Саша", "address_form": "feminine",
                        "llm_character": "brief"})
kept = {item["id"]: item["detail"]
        for group in privacy.inventory(store) if group["id"] == "settings"
        for item in group["items"]}
check("заданное имя видно среди того, что о человеке известно",
      kept.get("user_name") == "Саша", f"| {kept.get('user_name')!r}")
check("и род обращения тоже",
      kept.get("address_form") == "feminine", f"| {kept.get('address_form')!r}")
check("и выбранный характер",
      kept.get("llm_character") == "brief", f"| {kept.get('llm_character')!r}")

print()
print("ИТОГО ошибок:", fails)
sys.exit(1 if fails else 0)
