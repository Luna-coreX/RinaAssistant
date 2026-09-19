# -*- coding: utf-8 -*-
"""
D01: the product page says what is true (plan item `4.0b-D01`).

The page is read by somebody deciding whether to try the thing, and by a
developer deciding whether to write a plugin for it. Everything on it is
believed without checking — and that is exactly why it rots: the code moves
on, the sentence stays, and the sentence is what the reader takes away. It
had already happened to the README, which is the page this one grew out of:
"eleven system actions" when there were sixteen, screenshots of an interface
that had been redesigned away.

So the page is checked against the code rather than against a list somebody
maintains beside it:

    figures      against `SYSTEM_ACTIONS`, `COMMAND_TYPES`, the plugin
                 manifests, the shell's strings, the recorded utterances
                 and the check suite itself
    the API      against `plugins/api.py`, `core/permissions.py`, the page
                 and settings vocabularies, and the protocol's contract —
                 both ways, so a hook added in code and left undocumented
                 turns this red as surely as a hook deleted from code
    version      against the shell's version
    sections     the Russian page against the English one, set and order,
                 for the landing and for the API page alike
    links        local ones reach a file, repository ones a document that
                 is still in the tree
    other hosts  there are none at all
    promises     the one about money and the one about telemetry are on
                 both pages

**Being in two languages is checked separately, because that is what comes
apart in silence.** One page gets edited and the other is remembered later;
a release on, they describe different programs, and the only person who
would notice reads both — that is, nobody.

To run:
    python tools/check_site.py
"""
import io
import json
import os
import re
import subprocess
import sys
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
os.chdir(ROOT)

from console import use_utf8
use_utf8()

SITE = os.path.join(ROOT, "site")

#: The pages of the site, by the name the report calls them.
#:
#: Two pairs: what the product is, and how to build on it. Each pair is
#: compared with itself across the two languages.
LANDING = {
    "русская": os.path.join(SITE, "index.html"),
    "английская": os.path.join(SITE, "en", "index.html"),
}
API = {
    "русская API": os.path.join(SITE, "api", "index.html"),
    "английская API": os.path.join(SITE, "en", "api", "index.html"),
}
PAGES = dict(LANDING, **API)

fails = 0


def check(label, ok, detail=""):
    """One line of the report.

    The explanation is printed only when the check falls over: beside a
    green line it reads as though the thing it warns about had been found,
    and a report that has to be re-read is a report that stops being read.
    """
    global fails
    if not ok:
        fails += 1
    print(("OK   " if ok else "FAIL "), label, detail if not ok else "")


def read(path):
    return io.open(path, encoding="utf-8").read()


print("=== страница на месте ===")

#: What the site is made of. The generated and copied parts are checked by
#: `gen_site.py --check`; here it matters only that they exist, because
#: everything below reads them.
PARTS = {
    "site/index.html": "русская страница",
    "site/en/index.html": "английская страница",
    "site/api/index.html": "русская документация API",
    "site/en/api/index.html": "английская документация API",
    "site/style.css": "оформление",
    "site/tokens.css": "значения из дизайн-системы",
    "site/_headers": "заголовки ответов",
    "site/README.md": "как это устроено и как публикуется",
}
for name, what in PARTS.items():
    path = os.path.join(ROOT, name.replace("/", os.sep))
    ok = os.path.isfile(path) and os.path.getsize(path) > 200
    check(f"{what}: {name}", ok, "" if ok else "| нет файла или он пуст")

if not all(os.path.isfile(path) for path in PAGES.values()):
    print()
    print("ИТОГО ошибок:", fails, "| без страниц проверять нечего")
    sys.exit(1)

pages = {name: read(path) for name, path in PAGES.items()}
lower = {name: text.lower() for name, text in pages.items()}

# Nothing else is in the delivery. `site/` is uploaded whole, so a file
# that ends up in it is published — and a file nobody asked for is
# either weight or a leak. `Onest-Bold.ttf` sat there unused: the
# generator never copied it, no page is set in it, and `--check` said
# nothing because it only looks at what it does copy. The screenshots
# would have come back the same way.
print()
print("=== в раздаче нет лишнего ===")

import gen_site

expected = set(gen_site.copies())
expected |= {"tokens.css", "wires.svg", "style.css", "_headers", "README.md",
             "index.html", "en/index.html", "api/index.html",
             "en/api/index.html"}
expected |= {"docs/%s/index.html" % slug
             for slug, *_rest in gen_site.PAPERS}

found = set()
for here, dirs, names in os.walk(SITE):
    dirs[:] = [one for one in dirs if one != ".git"]
    for name in names:
        found.add(os.path.relpath(os.path.join(here, name),
                                  SITE).replace(os.sep, "/"))

extra = sorted(found - expected)
check("в site/ нет файлов, которых никто не просил", not extra,
      "| лишние: " + ", ".join(extra))
lost = sorted(expected - found)
check("и нет недостающих", not lost, "| нет: " + ", ".join(lost))

# ---------------------------------------------------------------------------
# The sections the task asked for
# ---------------------------------------------------------------------------
#
# `4.0b-D01` names six things the page has to carry: value, download,
# capabilities, privacy, documentation, plans. Written out as identifiers
# rather than left to the eye — otherwise "the page covers it" is decided by
# whoever is looking, and they wrote it.
print()
print("=== разделы, которых требует задача ===")

DEMANDED = {
    "value": "ценность",
    "download": "скачивание",
    "capabilities": "возможности",
    "privacy": "приватность",
    "docs": "документация",
    "plans": "планы",
}

SECTION = re.compile(r'<section[^>]*\bid="([^"]+)"')
#: Any anchorable id, not only a section's: the skip link points at the
#: page's `main`, and a check that knew only sections called that broken.
ANCHOR = re.compile(r'\bid="([^"]+)"')
sections = {name: SECTION.findall(text) for name, text in pages.items()}

for where in LANDING:
    missing = [what for key, what in DEMANDED.items()
               if key not in sections[where]]
    check(f"{where} страница несёт всё требуемое", not missing,
          "| нет разделов: " + ", ".join(missing))

# Both pages of a pair carry the same sections, in the same order. A page
# that quietly lost one is the usual shape of bilingual rot: nobody reads
# both, so nobody sees it.
for pair, (one, two) in (("страницы продукта", tuple(LANDING)),
                         ("страницы API", tuple(API))):
    check(f"разделы обеих версий совпадают: {pair}",
          sections[one] == sections[two],
          f"| {one}: {sections[one]} | {two}: {sections[two]}")

# The direction the world was built to is written into the markup itself
# (`4.0b-D01`). A page that lost that contract cannot be audited against
# anything later.
for where, text in pages.items():
    check(f"{where}: контракт направления на месте",
          "THESIS:" in text and "a2a26a10" in text,
          "| из разметки пропал контракт направления")

# ---------------------------------------------------------------------------
# The figures on the label strip
# ---------------------------------------------------------------------------
#
# Every figure is asked of the code. They are compared as a list, in order:
# a check that only asked "is 16 somewhere on the page" would go on passing
# after the numbers were shuffled between their legends.
print()
print("=== показания сверены с кодом ===")

sys.path.insert(0, ROOT)
from voice.user_commands import COMMAND_TYPES, STEP_ONLY, SYSTEM_ACTIONS
from core.permissions import PERMISSIONS, PLUGIN_FORBIDDEN
from plugins.api import API_VERSION, Plugin, PluginContext, PluginManifest, PluginTool
from plugins.page_spec import KINDS as PAGE_KINDS

#: Plugins that ship but are not a capability of the product.
#:
#: By name and with a reason, in the manner of `regress.py`: a silent
#: exception turns a rule into a wish. If the demo ever becomes a real
#: plugin, the line goes and the figure on the page changes with it.
NOT_SHIPPED = {
    "weather_api_test": "образец API v4 для тех, кто пишет плагины",
}


def bundled():
    """The plugins the page counts, by their manifest name."""
    out = {}
    for name in sorted(os.listdir(os.path.join(ROOT, "plugins"))):
        if name in NOT_SHIPPED:
            continue
        manifest = os.path.join(ROOT, "plugins", name, "plugin.json")
        if not os.path.isfile(manifest):
            continue
        with io.open(manifest, encoding="utf-8") as handle:
            out[name] = json.load(handle).get("name", "")
    return out


def tongues():
    """The interface languages: the four translations plus the source one."""
    with io.open(os.path.join(ROOT, "shell", "Rina.Shell", "Strings",
                              "interface.json"), encoding="utf-8") as handle:
        strings = json.load(handle)
    found = set()
    for value in strings.values():
        found.update(value)
    return len(found) + 1


def utterances():
    """The recorded phrases that pin the parsing down."""
    with io.open(os.path.join(ROOT, "docs", "golden", "utterances.json"),
                 encoding="utf-8") as handle:
        return len(json.load(handle)["cases"])


def suite():
    """How many checks the suite has — asked of the suite itself.

    Counting the files here would be a second implementation of what
    `regress.py` does, and the page's sentence is about the suite, not
    about a directory listing.
    """
    try:
        listed = subprocess.run(
            [sys.executable, os.path.join(ROOT, "tools", "regress.py"),
             "--list"],
            capture_output=True, text=True, encoding="utf-8",
            timeout=180).stdout or ""
    except subprocess.TimeoutExpired:
        return None
    found = re.search(r"всего:\s*(\d+)", listed)
    return int(found.group(1)) if found else None


def contract():
    """The protocol's machine-readable contract."""
    with io.open(os.path.join(ROOT, "docs", "protocol", "contract-v1.json"),
                 encoding="utf-8") as handle:
        return json.load(handle)


def settings_kinds():
    """The kinds of settings field the plugin API offers."""
    source = read(os.path.join(ROOT, "plugins", "settings_spec.py"))
    return sorted(set(re.findall(r'kind="([a-z]+)"', source)))


plugins = bundled()
checks_in_suite = suite()
wire = contract()
setting_kinds = settings_kinds()

STRIP = re.compile(r'<div class="strip"[^>]*>(.*?)</div>\s*</div>', re.S)


def strip_figures(text):
    """The numbers of the label strip, in the order the page shows them."""
    found = STRIP.search(text)
    if not found:
        return None
    return [int(one) for one in re.findall(r"<b>(\d+)</b>", found.group(1))]


#: The product strip, in the order the landing shows it.
PRODUCT = [
    (len(SYSTEM_ACTIONS), "системные действия"),
    (len(COMMAND_TYPES), "виды шага"),
    (len(plugins), "плагины в поставке"),
    (tongues(), "языки интерфейса"),
    (utterances(), "записанные фразы"),
    (checks_in_suite, "проверки в наборе"),
]

#: The API strip, likewise.
SURFACE = [
    (API_VERSION, "версия плагинного API"),
    (len(PAGE_KINDS), "виды элемента страницы"),
    (len(PERMISSIONS), "разрешения в каталоге"),
    (len(wire["methods"]), "методы протокола"),
    (len(wire["events"]), "события"),
    (len(wire["errors"]), "ошибки"),
]

check("набор сказал, сколько в нём проверок", checks_in_suite is not None,
      "| без этого числа страница не сверяется")

for group, wanted_all, where_all in (("продукт", PRODUCT, LANDING),
                                     ("API", SURFACE, API)):
    wanted = [number for number, _ in wanted_all if number is not None]
    for where in where_all:
        said = strip_figures(pages[where])
        if said is None:
            check(f"{where}: полоса показаний на месте", False)
            continue
        if len(said) == len(wanted) + 1:
            said = said[:len(wanted)]
        check(f"{where}: показания сходятся с кодом ({group})", said == wanted,
              f"| на странице {said}, в коде {wanted} "
              f"({', '.join(what for _, what in wanted_all)})")

# ---------------------------------------------------------------------------
# The numbers written out in prose
# ---------------------------------------------------------------------------
#
# The strip is not the only place with a figure. A page for people writes
# some of them as words — "sixteen actions" reads, "16 actions" reports —
# and a word rots exactly as quietly as a digit.
print()
print("=== числа в прозе ===")

#: Number -> the word each page writes it with.
#:
#: Not a convenience: the collocation is what is checked, and a bare digit
#: found somewhere else on the page would let "sixteen actions" rot while
#: the check stayed green. When a number grows out of this table the check
#: says so — and it says so exactly when the page needs editing anyway.
WORDS = {
    6: {"русская": "шесть", "английская": "six"},
    7: {"русская": "семь", "английская": "seven"},
    13: {"русская": "тринадцать", "английская": "thirteen"},
    16: {"русская": "шестнадцать", "английская": "sixteen"},
    17: {"русская": "семнадцать", "английская": "seventeen"},
    22: {"русская": "двадцать две", "английская": "twenty-two"},
    23: {"русская": "двадцать три", "английская": "twenty-three"},
}

model = read(os.path.join(ROOT, "docs", "security", "THREAT-MODEL.md"))
threats = len(re.findall(r"^### T-", model, re.MULTILINE))
surfaces = len(re.findall(r"^## Поверхность", model, re.MULTILINE))

#: The figure, how each page says it, what it is about, and where it is said.
PROSE = [
    (len(SYSTEM_ACTIONS),
     {"русская": "{} действий системы", "английская": "{} system actions"},
     "системных действий", LANDING),
    (len(plugins),
     {"русская": "в поставке {}", "английская": "{} ship with her"},
     "плагинов в поставке", LANDING),
    (surfaces,
     {"русская": "{} поверхностей", "английская": "{} surfaces"},
     "поверхностей в модели угроз", LANDING),
    (threats,
     {"русская": "{} угрозы", "английская": "{} threats"},
     "угроз в модели угроз", LANDING),
    (len(PAGE_KINDS),
     {"русская": "{} видов", "английская": "{} kinds"},
     "видов элемента страницы", API),
]

for number, templates, what, where_all in PROSE:
    word = WORDS.get(number)
    if not word:
        check(f"{what} — {number}", False,
              "| для этого числа в таблице нет слова: допишите его")
        continue
    for where in where_all:
        tongue = "английская" if where.startswith("английская") else "русская"
        phrase = templates[tongue].format(word[tongue])
        check(f"{where}: {what} — «{phrase}»", phrase in lower[where],
              "| число на странице отстало от кода")

# The plugins are named, not only counted. A count survives a rename; a name
# does not, and the page names all six.
for folder, title in plugins.items():
    check(f"русская страница называет плагин «{title}»",
          title and title in pages["русская"],
          f"| plugins/{folder}/plugin.json зовётся иначе, чем страница")

# ---------------------------------------------------------------------------
# What the page promises each plugin does
# ---------------------------------------------------------------------------
#
# The count was asked of the code from the first day; the claim beside the
# count was not. The strip said "у каждого своя страница" while one plugin
# of the six has a section, two put a tile on the home screen and three
# only answer by voice. A figure is easy to check, which is exactly why
# the figures were right and the sentence next to them was wrong.
#
# Which plugin the prose means is said with an attribute, because
# «Заметок» is not «Заметки»: a check that matched the manifest title
# literally would be a check about Russian declension, and it would go
# green the moment someone declined the word. The marker is invisible on
# the page and wraps the words themselves, so there is no second copy of
# the claim to keep in step.
print()
print("=== что страница обещает каждому плагину ===")

#: Hook -> what the page calls that ability, and how the code shows it.
ABILITIES = {
    "page": ("свой раздел", re.compile(r"^\s*def\s+page\s*\(", re.M)),
    "home": ("плитка на главном экране",
             re.compile(r"^\s*def\s+home\s*\(", re.M)),
}


def defines(folder, pattern):
    """Does this plugin's own code define that hook?"""
    where = os.path.join(ROOT, "plugins", folder)
    return any(pattern.search(read(os.path.join(where, name)))
               for name in sorted(os.listdir(where)) if name.endswith(".py"))


for hook, (ability, pattern) in ABILITIES.items():
    in_code = {folder for folder in plugins if defines(folder, pattern)}
    for where in LANDING:
        said = set(re.findall(f'data-plugin-{hook}="([^"]+)"', pages[where]))
        check(f"{where}: {ability} — ровно у тех плагинов, что и в коде",
              said == in_code,
              f"| страница: {sorted(said) or 'ни у кого'} "
              f"| код: {sorted(in_code) or 'ни у кого'}")

# ---------------------------------------------------------------------------
# The engines the page offers against the engines the program offers
# ---------------------------------------------------------------------------
#
# The page named five recognisers where the settings offer three. Google
# and PocketSphinx open a microphone of their own, and sound here arrives
# from the shell, so 4.0 stopped offering them (`4.0-E05`) — and the page
# went on naming them, together with a line in the privacy section about a
# recorded piece of speech going to Google. A list is among the most
# believed things on a product page, and this one was wrong in the
# direction that costs trust.
#
# The lists are read as lists: comma-separated, between the two words that
# introduce and end them. Prose that stops being a list turns this red,
# and that is the right moment to look at it.
print()
print("=== движки речи и слуха ===")

import core.settings_schema as settings_schema

#: Engine key -> the word each page uses for it.
#:
#: A word of the page, not the title from the settings: the page writes
#: «молча» where the settings write «Без голоса (только текст)», and
#: neither should be made to sound like the other. An engine missing from
#: this table is reported as missing from it — the table is part of the
#: check, not a convenience for it.
ENGINE_WORDS = {
    "silent": {"русская": "молча", "английская": "silent"},
    "pyttsx3": {"русская": "pyttsx3", "английская": "pyttsx3"},
    "edge": {"русская": "Edge Neural TTS", "английская": "Edge Neural TTS"},
    "gtts": {"русская": "gTTS", "английская": "gTTS"},
    "piper": {"русская": "Piper", "английская": "Piper"},
    "vosk": {"русская": "Vosk", "английская": "Vosk"},
    "whisper": {"русская": "Whisper", "английская": "Whisper"},
    "disabled": {"русская": "выключен", "английская": "off"},
}

#: Setting -> what the report calls it, and the words its list sits between.
SPOKEN = {
    "tts_engine": ("речь", {"русская": ("Речь:", "."),
                            "английская": ("Speech:", ".")}),
    "stt_engine": ("слух", {"русская": ("Слух:", "—"),
                            "английская": ("Hearing:", "—")}),
}

for key, (what, edges) in SPOKEN.items():
    offered = [one["value"] for one in settings_schema.options_for(key, {})]
    unknown = [one for one in offered if one not in ENGINE_WORDS]
    check(f"{what}: у каждого движка есть слово для страницы", not unknown,
          f"| нет в таблице: {unknown} — допишите слово")
    if unknown:
        continue
    for where in LANDING:
        opens, closes = edges[where]
        text = " ".join(pages[where].split())
        at = text.find(opens)
        end = text.find(closes, at + len(opens)) if at >= 0 else -1
        if at < 0 or end < 0:
            check(f"{where}: {what} — список на месте", False,
                  f"| между «{opens}» и «{closes}» ничего не нашлось")
            continue
        # Compared as sets: the order on the page is a matter of reading,
        # the membership is a matter of fact.
        said = {one.strip() for one in
                text[at + len(opens):end].split(",") if one.strip()}
        want = {ENGINE_WORDS[one][where] for one in offered}
        check(f"{where}: {what} — те же движки, что в настройках",
              said == want,
              f"| страница: {sorted(said)} | настройки: {sorted(want)}")

# ---------------------------------------------------------------------------
# The API page against the API
# ---------------------------------------------------------------------------
#
# Both ways round, and that is the point. A hook renamed in code turns this
# red because the page no longer names it; a hook **added** to code turns it
# red because the page does not know about it yet. Documentation that only
# ever catches deletions is documentation that quietly falls behind.
print()
print("=== документация API против самого API ===")

#: Methods of `Plugin` that are conveniences rather than hooks, by name and
#: with a reason: they call through to `ctx` and a plugin may ignore them.
HELPERS = {
    "log": "короткий путь к ctx.log",
    "respond": "короткий путь к ctx.respond",
    "setting": "чтение своей настройки со схемой",
}

#: Hooks are what a plugin overrides with a method; the two page fields are
#: values it sets instead. Both are public API, and the page owes both a
#: line — `page_title` and `page_icon` were on neither table until this
#: check asked the class rather than the author.
public = [n for n in dir(Plugin) if not n.startswith("_") and n not in HELPERS]
hooks = sorted(n for n in public if callable(getattr(Plugin, n)))
fields = sorted(n for n in public if not callable(getattr(Plugin, n)))
services = sorted(n for n in dir(PluginContext) if not n.startswith("_"))
tool_fields = sorted(PluginTool.__dataclass_fields__)
#: `path` is filled in by the manager, not written by the plugin's author.
manifest_fields = sorted(n for n in PluginManifest.__dataclass_fields__
                         if n != "path")

for where in API:
    for name in hooks:
        check(f"{where}: хук {name} описан", name in pages[where],
              "| хук есть в plugins/api.py, а на странице его нет")
    for name in fields:
        check(f"{where}: поле {name} описано", name in pages[where],
              "| поле есть в классе Plugin, а на странице его нет")
    for name in services:
        check(f"{where}: служба ctx.{name} описана", name in pages[where],
              "| служба есть в PluginContext, а на странице её нет")
    for name in tool_fields:
        check(f"{where}: поле инструмента {name} описано",
              name in pages[where],
              "| поле есть в PluginTool, а на странице его нет")
    for name in manifest_fields:
        check(f"{where}: поле манифеста {name} описано",
              name in pages[where],
              "| поле есть в PluginManifest, а на странице его нет")
    for name in PAGE_KINDS:
        check(f"{where}: вид элемента {name} описан",
              f"<td>{name}</td>" in pages[where],
              "| вид есть в словаре страницы, а в таблице его нет")
    for name in setting_kinds:
        check(f"{where}: вид настройки {name} описан",
              f"<td>{name}</td>" in pages[where],
              "| вид есть в settings_spec.py, а в таблице его нет")

# Every permission of the catalogue is on the page, and the four that a
# plugin never gets are marked as never. A table that lists a forbidden
# permission as granted is worse than a table that omits it: somebody will
# write a plugin against it.
ROW = re.compile(r"<tr><td>([a-z.]+)</td>(.*?)</tr>", re.S)
for where in API:
    rows = {name: body for name, body in ROW.findall(pages[where])}
    for name in sorted(PERMISSIONS):
        body = rows.get(name)
        check(f"{where}: разрешение {name} в таблице", body is not None,
              "| разрешение есть в каталоге, а на странице его нет")
        if body is None:
            continue
        forbidden = 'class="no"' in body
        check(f"{where}: {name} помечено верно",
              forbidden == (name in PLUGIN_FORBIDDEN),
              "| страница обещает плагину то, чего ему не дают"
              if forbidden is False else
              "| страница отнимает у плагина то, что ему выдаётся")

# The protocol's counts, each in its own cell rather than anywhere on the
# page: a digit found loose in prose would let the table rot.
for where in API:
    for key, what in (("methods", "методов"), ("events", "событий"),
                      ("errors", "ошибок"), ("capabilities", "возможностей"),
                      ("stream_kinds", "видов потока")):
        number = len(wire[key])
        check(f"{where}: {what} в контракте — {number}",
              f"<td>{number}</td>" in pages[where],
              "| число в таблице отстало от contract-v1.json")
    check(f"{where}: версия протокола {wire['protocol_version']}",
          f"<code>contract-v{wire['protocol_version']}.json</code>"
          in pages[where] or f"contract-v{wire['protocol_version']}.json"
          in pages[where],
          "| страница ссылается на другую версию контракта")

# ---------------------------------------------------------------------------
# The version
# ---------------------------------------------------------------------------
print()
print("=== версия ===")

props = read(os.path.join(ROOT, "shell", "Directory.Build.props"))
found = re.search(r"<Version>([^<]+)</Version>", props)
check("версия оболочки читается", found is not None, "| нечего сверять")
if found:
    version = found.group(1)
    for where, text in pages.items():
        check(f"{where}: версия {version}", version in text,
              "| страница пережила смену версии")

# ---------------------------------------------------------------------------
# Links
# ---------------------------------------------------------------------------
#
# Three kinds, and each goes wrong in its own way: a local one points at a
# file that is not there, a repository one at a document that has been
# renamed, an anchor at a section that has been removed.
print()
print("=== ссылки ведут туда, где что-то есть ===")

REPO = "https://github.com/Luna-coreX/RinaAssistant"
BLOB = REPO + "/blob/HEAD/"

#: The only hosts the page may point a reader at.
#:
#: Not a whitelist for tidiness: the page promises that nothing on it comes
#: from anywhere else, and an address slipped in later is exactly what that
#: promise is about.
ALLOWED = {"github.com", "ollama.com"}

TARGET = re.compile(r'(?:href|src)="([^"]+)"')


def resolve(target, base):
    """A local link as a path on disk. A directory means its index."""
    if target.startswith("/"):
        path = os.path.join(SITE, target.lstrip("/").replace("/", os.sep))
    else:
        path = os.path.normpath(os.path.join(base, target))
    if target.endswith("/") or os.path.isdir(path):
        path = os.path.join(path, "index.html")
    return path


for where, text in pages.items():
    base = os.path.dirname(PAGES[where])
    ids = set(ANCHOR.findall(text))
    for target in TARGET.findall(text):
        target = target.strip()
        if target.startswith("#"):
            check(f"{where}: якорь {target}", target[1:] in ids,
                  "| раздела с таким именем нет")
            continue
        if target.startswith(("http://", "https://")):
            host = urlparse(target).netloc
            check(f"{where}: узел {host}", host in ALLOWED,
                  "| страница обещает, что чужих узлов на ней нет")
            if target.startswith(BLOB):
                inside = target[len(BLOB):].split("#")[0]
                check(f"{where}: документ {inside}",
                      os.path.exists(os.path.join(ROOT,
                                                  inside.replace("/", os.sep))),
                      "| ссылка на документ, которого в дереве нет")
            continue
        path = resolve(target.split("#")[0], base)
        check(f"{where}: файл {target}", os.path.isfile(path),
              "| нет такого файла в site/")

# The two pages of the site find each other. A documentation page nobody is
# sent to is a documentation page nobody reads.
for where in LANDING:
    base = os.path.dirname(PAGES[where])
    reached = {resolve(one.split("#")[0], base)
               for one in TARGET.findall(pages[where])
               if not one.startswith(("#", "http"))}
    wanted = API["английская API" if where.startswith("английская")
                 else "русская API"]
    check(f"{where}: ведёт к документации API", wanted in reached,
          "| со страницы продукта нет пути к API")
for where in API:
    home = "/en/" if where.startswith("английская") else '"/"'
    check(f"{where}: ведёт обратно к продукту", home in pages[where],
          "| со страницы API нет пути назад")

# The page shows no screenshots and carries no folder of them.
#
# The ones that were here were taken two releases before the page was
# written, and a visitor comparing them with what the installer gives
# would find a different program. Until the working mock-up replaces
# them, the interface is described in words — and a stale picture cannot
# creep back in through a copy nobody re-took.
print()
print("=== снимков на странице нет ===")

check("папки site/shots нет",
      not os.path.isdir(os.path.join(SITE, "shots")),
      "| снимки снова копируются в страницу")
for where, text in pages.items():
    check(f"{where}: не показывает снимков", "shots/" not in text,
          "| на странице снова снимок программы")

# ---------------------------------------------------------------------------
# What the page promises about itself
# ---------------------------------------------------------------------------
#
# A product page that says "nothing leaves your machine" and then loads a
# font from somebody else's service has refuted itself in the place where it
# is easiest to check — the browser's own panel. So: no scripts, no frames,
# no third-party anything. `_headers` forbids the same thing on the server's
# side; this forbids it in the markup.
print()
print("=== страница ничего не собирает ===")

FORBIDDEN = {
    "<script": "скрипт",
    "<iframe": "кадр",
    "<noscript": "заглушка для скрипта",
    "googletagmanager": "счётчик",
    "google-analytics": "счётчик",
    "fonts.googleapis": "шрифт со стороннего сервиса",
    "fonts.gstatic": "шрифт со стороннего сервиса",
    "cdn.jsdelivr": "чужая раздача",
    "unpkg.com": "чужая раздача",
    "yandex.ru/metrika": "счётчик",
    "onclick=": "обработчик события",
    "onload=": "обработчик события",
    # `style-src 'self'` does not admit the `style` attribute, so an inline
    # style is dropped on the live host and kept locally: the page looks
    # right here and loses its spacing there.
    'style="': "inline-стиль, который не переживёт политику ответов",
}
for where in pages:
    for mark, what in FORBIDDEN.items():
        check(f"{where}: нет — {what}", mark not in lower[where],
              f"| найдено «{mark}»")

# The policy is read from the header line itself, not from the file. The
# file explains the policy in a comment above it, and a check looking for
# the words anywhere would have been satisfied by the explanation while the
# header said `default-src *` — found by breaking it.
headers = read(os.path.join(SITE, "_headers"))
policy = next((line for line in headers.splitlines()
               if line.strip().startswith("Content-Security-Policy:")), "")
check("политика ответов объявлена", bool(policy),
      "| в _headers нет строки Content-Security-Policy")
check("политика запрещает всё, чего на странице нет",
      "default-src 'none'" in policy and "frame-ancestors 'none'" in policy,
      "| _headers перестал держать обещание страницы")

# ---------------------------------------------------------------------------
# The stylesheet takes its colours from the design system
# ---------------------------------------------------------------------------
#
# A colour typed into `style.css` is a second copy of the palette, and it
# parts company with the first one silently: a page a shade off looks like a
# page, not like a fault.
print()
print("=== цвет приходит из дизайн-системы ===")

style = read(os.path.join(SITE, "style.css"))

# **This check could not fail, and only breaking it said so.** The first
# edition carried a lookahead — `#[0-9a-f]{3,8}\b(?![^<]*>)` — borrowed from
# a check that reads markup, where it means "not inside a tag". A stylesheet
# has no tags and does have `>` in its selectors, so the lookahead was
# satisfied by any `>` further down the file and swallowed every match. A
# colour typed into `style.css` passed green.
#: A colour keyword is a colour too. `black` stood in the hero's mask stops
#: and this said nothing: it looked for hex and for `rgb(`, and a name is
#: neither. Comments are stripped first — prose about a colour is not one.
KEYWORDS = ("black", "white", "red", "green", "blue", "yellow", "orange",
            "purple", "gray", "grey", "silver", "gold", "pink", "brown")

bare = re.sub(r"/\*.*?\*/", "", style, flags=re.S)
literals = re.findall(r"#[0-9a-fA-F]{3,8}\b", bare)
literals += re.findall(r"\brgba?\(", bare)
literals += re.findall(r"\bhsla?\(", bare)
for word in KEYWORDS:
    literals += re.findall(r":[^;{}]*\b" + word + r"\b", bare)
check("в style.css нет цвета числом", not literals,
      f"| найдено: {literals[:4]}")

generated = read(os.path.join(SITE, "tokens.css"))
check("tokens.css порождён, а не написан",
      generated.startswith("/* Порождено tools/gen_site.py"),
      "| заголовок порождённого файла пропал")

# ---------------------------------------------------------------------------
# The documents the site publishes
# ---------------------------------------------------------------------------
#
# Eleven documents of the repository have a page each, generated from
# the `.md` by `tools/gen_site.py`. That generator's `--check` compares
# every page with a fresh rendering, so nothing here has to look at
# their contents; what it has to look at is the ring around them — that
# each one exists, that both landings lead to it, that the links inside
# go somewhere, and that a document has not quietly started loading
# something from a stranger.
print()
print("=== документы, опубликованные страницами ===")

import gen_site

papers = {}
for slug, source, title, _lead, _lang in gen_site.PAPERS:
    path = os.path.join(SITE, "docs", slug, "index.html")
    here = os.path.isfile(path)
    check(f"{title}: есть страница /docs/{slug}/", here,
          "| документ в списке, а страницы нет")
    if here:
        papers["документ " + slug] = path
    check(f"{title}: источник на месте",
          os.path.isfile(os.path.join(ROOT, source.replace("/", os.sep))),
          f"| нет файла {source}")
    for where in LANDING:
        check(f"{where} ведёт к /docs/{slug}/",
              f'href="/docs/{slug}/"' in pages[where],
              "| страница есть, а со страницы продукта на неё не попасть")

# Seven of the eleven are written in Russian and four in English, and a
# reader following a link from the other language has to know before
# they click. The mark is asked of the same table the pages are
# generated from, so a document that changes language cannot keep an
# out-of-date badge.
for where in LANDING:
    tongue = "ru" if where == "русская" else "en"
    marked = set(re.findall(r'data-tongue="(\w+)"', pages[where]))
    should = {lang for _s, _src, _t, _l, lang in gen_site.PAPERS
              if lang != tongue}
    count = len(re.findall(r'data-tongue=', pages[where]))
    want = sum(1 for _s, _src, _t, _l, lang in gen_site.PAPERS
               if lang != tongue)
    check(f"{where}: язык документа помечен там, где он не свой",
          marked == should and count == want,
          f"| пометок {count}, а документов на другом языке {want}")

written = {name: read(path) for name, path in papers.items()}

# They share the site's frame, and that is not decoration: without the
# rail there is no way off a document but the back button.
for name, text in written.items():
    check(f"{name}: каркас на месте",
          all(one in text for one in ('class="rail"', "<footer",
                                      'class="loom"', 'id="content"')),
          "| порождённая страница потеряла обвязку сайта")

# The links inside a document: local ones reach a file that exists,
# outside hosts are only the ones the rest of the site may reach. A
# document points at dozens of files in the tree, which is exactly why
# the generator rewrites its links — and a rewriting has to be checked.
for name, text in written.items():
    base = os.path.dirname(papers[name])
    ids = set(ANCHOR.findall(text))
    broken = []
    strangers = set()
    for target in TARGET.findall(text):
        target = target.strip()
        if target.startswith("#"):
            if target[1:] not in ids:
                broken.append(target)
            continue
        if target.startswith(("http://", "https://")):
            host = urlparse(target).netloc
            if host not in ALLOWED:
                strangers.add(host)
            continue
        if target.startswith("mailto:"):
            continue
        path = resolve(target.split("#")[0], base)
        if not os.path.isfile(path):
            broken.append(target)
    check(f"{name}: все ссылки куда-то ведут", not broken,
          "| никуда не ведут: " + ", ".join(sorted(set(broken))[:6]))
    check(f"{name}: чужих узлов нет", not strangers,
          "| " + ", ".join(sorted(strangers)))

# ---------------------------------------------------------------------------
# What the page says leaves, against what the code can dial
# ---------------------------------------------------------------------------
#
# The privacy section is the page's load-bearing claim, and it works only
# if the list is complete. It was not: model downloads, the update check,
# the music search and the weather sample all reach out, and none of the
# four were named. Nobody was careless — the list was written by hand
# from memory, and memory is exactly what a fifth outbound call will slip
# past.
#
# So the list is asked of the code. Every literal address in the core, the
# voice, the plugins and the shell is collected, and each host either has
# words on the page or a name and a reason below. A new address added
# anywhere turns this red on the next run.
print()
print("=== что уходит наружу — сверено с кодом ===")

REACHES = re.compile(r"https?://([A-Za-z0-9.-]+)")
SKIP_DIRS = {"bin", "obj", "__pycache__", "node_modules", ".git"}

#: Addresses that are not a destination, by name and with a reason.
NOT_A_DESTINATION = {
    "localhost": "адрес локальной модели; на странице он назван",
    "127.0.0.1": "то же самое, записанное числом",
    "x": "подставной адрес в проверках обновления",
    "example.com": "подставной адрес в проверках",
    "github.com": "ссылки, по которым человек переходит сам",
    "neurosync-foundry-portal.pages.dev": "адрес этой же страницы",
    "www.w3.org": "пространство имён разметки; никуда не ходит",
    "schemas.microsoft.com": "пространство имён XAML; никуда не ходит",
}

#: Host -> the words the page uses for it.
#:
#: A word, not an address: the page writes "the central bank's
#: website", and making it write `www.cbr-xml-daily.ru` would be
#: editing the text to suit the check. The addresses a person is better
#: off seeing in full are written in full.
HOST_WORDS = {
    "www.google.com": {"русская": "Веб-поиск", "английская": "Web search"},
    "www.bing.com": {"русская": "Веб-поиск", "английская": "Web search"},
    "duckduckgo.com": {"русская": "Веб-поиск", "английская": "Web search"},
    "yandex.ru": {"русская": "Веб-поиск", "английская": "Web search"},
    "www.youtube.com": {"русская": "YouTube", "английская": "YouTube"},
    "www.cbr.ru": {"русская": "Центробанка", "английская": "central bank"},
    "www.cbr-xml-daily.ru": {"русская": "Центробанка",
                             "английская": "central bank"},
    "alphacephei.com": {"русская": "alphacephei.com",
                        "английская": "alphacephei.com"},
    "huggingface.co": {"русская": "huggingface.co",
                       "английская": "huggingface.co"},
    "api.github.com": {"русская": "api.github.com",
                       "английская": "api.github.com"},
    "api.open-meteo.com": {"русская": "open-meteo.com",
                           "английская": "open-meteo.com"},
    "geocoding-api.open-meteo.com": {"русская": "open-meteo.com",
                                     "английская": "open-meteo.com"},
}


def dialled():
    """Every host the program's own code writes down, by where it is."""
    out = {}
    for base in ("core", "voice", "plugins", os.path.join("shell", "Rina.Shell")):
        for here, dirs, files in os.walk(os.path.join(ROOT, base)):
            dirs[:] = [one for one in dirs if one not in SKIP_DIRS]
            for name in files:
                if not name.endswith((".py", ".cs")):
                    continue
                path = os.path.join(here, name)
                for host in REACHES.findall(read(path)):
                    out.setdefault(host, set()).add(
                        os.path.relpath(path, ROOT).replace(os.sep, "/"))
    return out


PRIVACY = re.compile(r'<section id="privacy".*?</section>', re.S)

reached = dialled()
unknown = sorted(one for one in reached
                 if one not in HOST_WORDS and one not in NOT_A_DESTINATION)
check("у каждого узла из кода есть слово на странице", not unknown,
      "| впишите или объясните: "
      + "; ".join(f"{one} ({', '.join(sorted(reached[one]))})"
                  for one in unknown))

for where in LANDING:
    found = PRIVACY.search(pages[where])
    if not found:
        check(f"{where}: раздел приватности на месте", False)
        continue
    said = found.group(0)
    silent = sorted({HOST_WORDS[one][where] for one in reached
                     if one in HOST_WORDS and HOST_WORDS[one][where] not in said})
    check(f"{where}: назван каждый узел, куда программа может обратиться",
          not silent, "| на странице нет: " + ", ".join(silent))

# ---------------------------------------------------------------------------
# The inventory the page describes is the inventory the program shows
# ---------------------------------------------------------------------------
#
# The page listed five kinds of remembered thing; the program shows nine,
# and two of the five ("доверенные пути", "заметки") are not among them.
# On the one page whose whole point is completeness, a list made up from
# memory is the worst possible kind of mistake.
print()
print("=== опись «что Рина знает обо мне» ===")

KNOWS = read(os.path.join(ROOT, "shell", "Rina.Shell", "Pages",
                          "PrivacyPage.xaml.cs"))
groups = re.findall(r'"\w+" => \(S\("([^"]+)"\)', KNOWS)
check("группы описи прочитаны из оболочки", len(groups) >= 5,
      f"| нашлось {len(groups)}")

#: The words the page uses for a group, where they are not the title.
#:
#: The page speaks to a stranger and the program to its owner, so
#: «Статистика команд» reads as «статистика» in a sentence. Anything not
#: here has to appear as the program writes it.
AS_WRITTEN = {
    "Папки поиска программ": {"русская": "папки поиска",
                              "английская": "search folders"},
}
ENGLISH = json.loads(read(os.path.join(
    ROOT, "shell", "Rina.Shell", "Strings", "interface.json")))

#: The sentence itself, marked, because the words are not rare. The first
#: edition looked for the group's name anywhere on the page and passed
#: with «Напоминания» deleted from the inventory: the same word stands in
#: the paragraph about reminders two screens above.
SAYS = re.compile(r'<span class="line-which" data-knows="[^"]*">(.*?)</span>',
                  re.S)

for where in LANDING:
    found = SAYS.search(pages[where])
    check(f"{where}: опись на странице помечена", found is not None,
          "| нет строки с data-knows — искать не в чем")
    if not found:
        continue
    said = " ".join(found.group(1).split()).lower()
    lost = []
    for title in groups:
        if title in AS_WRITTEN:
            word = AS_WRITTEN[title][where]
        elif where == "английская":
            word = (ENGLISH.get(title) or {}).get("English", title)
        else:
            word = title
        if word.lower() not in said:
            lost.append(word)
    check(f"{where}: перечислено всё, что показывает сама программа",
          not lost, "| в описи на странице нет: " + ", ".join(lost))

# ---------------------------------------------------------------------------
# The plans point at the plan
# ---------------------------------------------------------------------------
#
# «Пульт с телефона» stood in the 5.0 row of a public page for a day. It
# is in no milestone: it was written from a half-remembered conversation.
# A plan on a product page is a promise, and the only cheap way to keep
# one honest is to make it cite the document it comes from.
print()
print("=== планы названы по пунктам ===")

PLAN = read(os.path.join(ROOT, "docs", "ROADMAP.md"))
ROWS = re.compile(r'<section id="plans".*?</section>', re.S)

for where in LANDING:
    block = ROWS.search(pages[where])
    if not block:
        check(f"{where}: раздел планов на месте", False)
        continue
    rows = len(re.findall(r'class="line-which"', block.group(0)))
    cited = re.findall(r'data-plan="([^"]+)"', block.group(0))
    check(f"{where}: каждая строка планов на что-то ссылается",
          len(cited) == rows, f"| строк {rows}, со ссылкой {len(cited)}")
    named = sorted({one for group in cited for one in group.split()})
    lost = [one for one in named if one + " " not in PLAN and one + "\u00b7" not in PLAN]
    check(f"{where}: каждый названный пункт есть в ROADMAP", not lost,
          "| в плане нет: " + ", ".join(lost))

# ---------------------------------------------------------------------------
# The English page says which language she is spoken to in
# ---------------------------------------------------------------------------
#
# The commands are Russian ones. For a reader of the English page that
# decides whether to install at all, and it went missing in a rewrite
# that was only meant to shorten the text.
# The whole sentence, not two words of it: "spoken to in Russian"
# also stands in the strip of facts under the headline, and a check
# looking for that much passed with the sentence deleted. A chip is not
# an explanation.
check("английская: сказано, на каком языке с ней говорят",
      "she is spoken to in russian" in lower["английская"],
      "| страница молчит о том, что команды русские")

# ---------------------------------------------------------------------------
# What the installer promises not to do
# ---------------------------------------------------------------------------
#
# Four promises about behaviour, made publicly and kept by the absence of
# four things in one file. Absence is what rots quietly: a `[Registry]`
# section added for a good reason would make the page lie.
print()
print("=== установщик не делает того, чего обещал не делать ===")

SETUP = read(os.path.join(ROOT, "packaging", "rina.iss"))
FORBIDDEN = {
    "[Registry]": "не трогает PATH и не регистрирует привезённый Python",
    "[Services]": "не ставит службу",
    "[UninstallRun]": "и ничего не запускает после удаления",
}
for section, promise in sorted(FORBIDDEN.items()):
    check(f"в rina.iss нет {section}: {promise}", section not in SETUP,
          "| страница обещает обратное")
check("установщик не просит прав администратора",
      "PrivilegesRequired=lowest" in SETUP,
      "| страница обещает установку в профиль пользователя")

# ---------------------------------------------------------------------------
# Motion cannot hide the page
# ---------------------------------------------------------------------------
#
# Blocks arrive and leave with the scroll, and an arrival is written by
# starting at `opacity: 0`. That is the one shape of animation that can
# take the page away: a browser without scroll timelines, a timeline that
# never attaches, a range that resolves wrong — and the reader is left
# with a working scrollbar and a black screen, with nothing to tell them
# why.
#
# So the rule is structural. Whatever sets `opacity: 0` sits inside
# `@supports (animation-timeline: …)`, which a browser drops whole when
# it cannot drive it; outside that guard the page is simply visible.
print()
print("=== движение не прячет страницу ===")


# The loom is one layer on every page, and its shape lives in a file of
# its own. The first edition kept the geometry inline in all four pages
# and compared the copies; the second painted a layer and cut it with
# the file as a mask, and a masked layer eleven thousand points tall
# rasterised in pieces — rectangles of paint on screen and five-second
# frames. Now it is a tile of background, and the colour lives inside
# the file, which is why the file is generated from the same tokens.
lost = sorted(name for name, text in pages.items()
              if '<div class="loom"' not in text)
check("жгут есть на каждой странице", not lost, "| нет на: " + ", ".join(lost))

WIRES = os.path.join(SITE, "wires.svg")
check("рисунок жгута лежит в site/wires.svg", os.path.isfile(WIRES),
      "| маски нет, и фон страницы пуст")

if os.path.isfile(WIRES):
    shape = read(WIRES)
    check("оформление берёт его плиткой",
          'background-image: url("wires.svg")' in style,
          "| файл есть, но страница его не просит")
    drawn = len(re.findall(r"<path", shape))
    check("в жгуте есть провода", drawn >= 4, f"| путей {drawn}")
    # The colour inside the file is the hairline and nothing else: it
    # is a second copy of a value, and what holds it in place is that
    # the file is generated. `gen_site.py --check` compares it byte for
    # byte; this says which colour it has to be, so that an edit to the
    # generator cannot quietly mean something else.
    paints = {one.lower() for one in re.findall(r"#[0-9a-fA-F]{6}", shape)}
    found = re.search(r"--hair:\s*(#[0-9a-fA-F]{6})",
                      read(os.path.join(SITE, "tokens.css")))
    hair = found.group(1).lower() if found else ""
    check("в жгуте только цвет волосяной линии", paints == {hair},
          f"| в файле {sorted(paints)}, а --hair это {hair}")
    # The tile meets itself: every wire leaves the bottom edge where it
    # entered the top. Otherwise `repeat-y` puts a seam across the page
    # once every 1400 points — often enough to be wrong, rarely enough
    # not to be noticed at first.
    box = re.search(r'viewBox="0 0 (\d+) (\d+)"', shape)
    check("у плитки объявлен размер", box is not None)
    if box:
        tall = box.group(2)
        ends = re.findall(r'd="M (\d+) 0 C [^"]*?, (\d+) ' + tall + r'"', shape)
        check("плитка сходится сама с собой по вертикали",
              len(ends) == drawn and all(one == two for one, two in ends),
              "| провод входит и выходит в разных местах — будет шов")


def rules(text):
    """(selector, body, the at-rules around it) for every rule in a sheet.

    A scanner and not a regular expression: what matters here is which
    `@`-rules a declaration sits inside, and that is exactly what a
    regular expression cannot see. `@keyframes` is skipped whole, because
    `opacity: 0` in a keyframe is the animation itself.
    """
    out = []
    stack = []
    head = ""
    at = 0
    end = len(text)
    while at < end:
        if text.startswith("/*", at):
            shut = text.find("*/", at + 2)
            at = end if shut < 0 else shut + 2
            continue
        one = text[at]
        if one == "{":
            name = " ".join(head.split())
            head = ""
            if name.startswith(("@keyframes", "@font-face")):
                depth = 1
                at += 1
                while at < end and depth:
                    depth += {"{": 1, "}": -1}.get(text[at], 0)
                    at += 1
                continue
            if name.startswith("@"):
                stack.append(name)
                at += 1
                continue
            shut = text.find("}", at)
            out.append((name, text[at + 1:shut], tuple(stack)))
            at = shut + 1
            continue
        if one == "}":
            if stack:
                stack.pop()
            head = ""
            at += 1
            continue
        head += one
        at += 1
    return out


def keyframes(text):
    """Every `@keyframes` set in a sheet, by name, with its body."""
    out = {}
    for found in re.finditer(r"@keyframes\s+([\w-]+)\s*\{", text):
        depth, at = 0, found.end() - 1
        while at < len(text):
            depth += {"{": 1, "}": -1}.get(text[at], 0)
            at += 1
            if not depth:
                break
        out[found.group(1)] = text[found.end():at]
    return out


#: Selectors allowed to start invisible, by name and with a reason.
#:
#: Decoration only. A rule that hides something a person came to read
#: does not belong on this list, however convenient it would be.
MAY_BE_INVISIBLE = {
    "body::after": "свет, проходящий по плите: он и начинается погашенным",
    ".loom .spark": "сигнал в жгуте: идёт по часам, а не по прокрутке",
}

GUARD = "animation-timeline"
DARK = re.compile(r"opacity\s*:\s*0(?:\.0+)?\s*(?:;|\n|\})")
PLAYS = re.compile(r"animation(?:-name)?\s*:([^;]+)")

#: Keyframe sets that begin at nothing. A rule that plays one of these
#: needs the guard: the page would start blank without it.
GOES_DARK = {name for name, body in keyframes(style).items()
             if DARK.search(body)}

# The first edition looked for `opacity: 0` in the rule itself and found
# none — it is in the keyframes, and the rule only names them. The break
# that was supposed to catch this (the guard swapped for `@media screen`)
# went through green, which is the whole reason the break is run.
hidden = []
for name, body, around in rules(style):
    if name in MAY_BE_INVISIBLE:
        continue
    played = {one for sets in PLAYS.findall(body)
              for one in re.findall(r"[\w-]+", sets)}
    if not (played & GOES_DARK):
        continue
    if not any(GUARD in one for one in around):
        hidden.append(name)

check("содержимое не гасится вне @supports", not hidden,
      "| гасят и без таймлайнов: " + ", ".join(hidden))
check("наборы кадров, начинающиеся с нуля, найдены", bool(GOES_DARK),
      "| проверка выше ничего не сторожит")

# Two sets of keyframes under one name: the later one wins, silently,
# and whatever asked for the first plays the second instead. It happened
# while this page was being written — a new `patch-in` for the section
# rule took the name of the one that draws the cord in the first screen,
# and the only sign was that the cord stopped being drawn.
names = re.findall(r"@keyframes\s+([\w-]+)", style)
twice = sorted({one for one in names if names.count(one) > 1})
check("у каждого набора кадров своё имя", not twice,
      "| под одним именем: " + ", ".join(twice))

# And the name a rule plays has to exist. A misspelt one is an animation
# that quietly does nothing: the property keeps its ordinary value, the
# page looks almost right, and nothing anywhere says a word.
#
# Reading the name out of the shorthand means throwing away everything
# that is not a name — times, curves, counts, fill modes — so the list
# below is part of the check and not a convenience: a word missing from
# it turns up as «набор кадров … не объявлен», which is the wrong
# message but the right colour.
NOT_A_NAME = {
    "linear", "ease", "ease-in", "ease-out", "ease-in-out",
    "step-start", "step-end", "both", "forwards", "backwards", "none",
    "infinite", "normal", "reverse", "alternate", "alternate-reverse",
    "running", "paused",
}
SHED = re.compile(r"[a-z-]+\([^()]*\)")

known = set(names)
called = set()
for _name, body, _around in rules(style):
    for sets in PLAYS.findall(body):
        for part in SHED.sub(" ", sets).split(","):
            # Not after a digit: `1100ms` is a duration, and the `ms`
            # in it was being read as a set of keyframes.
            for word in re.findall(r"(?<![\w.])[A-Za-z][\w-]*", part):
                if word not in NOT_A_NAME:
                    called.add(word)

unknown = sorted(called - known)
check("каждый играемый набор кадров объявлен", not unknown,
      "| не объявлен: " + ", ".join(unknown))

idle = sorted(known - called)
check("лишних наборов кадров нет", not idle,
      "| никто не играет: " + ", ".join(idle))

#: Keyframe sets that live under the page and never carry ink.
MAY_STAY_DIM = {
    "plate-light": "свет по плите: в полную силу он спорил бы с набором",
}

# And the other half: what starts at nothing has to come back. A set of
# keyframes that never reaches full ink passes the rule above and still
# leaves the page grey.
for name, body in sorted(keyframes(style).items()):
    if "opacity" not in body or name in MAY_STAY_DIM:
        continue
    check(f"кадры {name} доводят до полных чернил",
          re.search(r"opacity\s*:\s*1\s*[;}\n]", body) is not None,
          "| гасят и не возвращают")

# ---------------------------------------------------------------------------
# Contrast, the way the program checks its own
# ---------------------------------------------------------------------------
#
# The program has had this since `4.0-R03`; the page did not, and the first
# review found by eye what a machine should have found: a badge set in the
# faint ink on the plate at 3.8:1. Contrast is declared, not hoped for.
print()
print("=== контраст пар, которыми набрана страница ===")

import nebula

values = dict(re.findall(r"--([a-z0-9-]+):\s*(#[0-9a-fA-F]{6})", generated))


def ratio(one, two):
    """WCAG 2.1, the same formula the program's check uses."""
    first, second = nebula.luminance(one), nebula.luminance(two)
    light, dark = max(first, second), min(first, second)
    return (light + 0.05) / (dark + 0.05)


#: Ink on surface, and what the pair carries. The threshold follows the
#: work the pair does on the screen: 4.5 for text, 3.0 for what is only a
#: line or a mark.
PAIRS = [
    ("ink", "ground", 4.5, "основной текст на земле"),
    ("ink", "plate", 4.5, "основной текст на плите"),
    ("ink-soft", "ground", 4.5, "легенды на земле"),
    ("ink-soft", "plate", 4.5, "легенды на плите"),
    ("ink-faint", "ground", 4.5, "номер строки и время на земле"),
    ("ink-faint", "hole", 4.5, "пояснение в блоке кода"),
    ("strip-ink", "strip", 4.5, "буквы наборной этикетки"),
    ("lamp", "plate", 4.5, "метка «выдаётся»"),
    ("cord", "ground", 3.0, "шнур и рамка фокуса"),
    # The jack's label stands directly on the drilled field, so a glyph
    # can land on a chamfer. Soft ink scores 2.39 there, which is why
    # none of it stands over the field at all; full ink is measured here.
    ("ink", "rim", 4.5, "подпись поверх просверленного поля"),
]

#: Pairs deliberately not in the table, by name and with a reason.
#:
#: The drilled field is **material**, not a control and not a graphic the
#: reader has to make out: nothing on the page depends on counting its
#: holes. WCAG asks 3:1 of controls and of meaningful graphics, and a panel
#: with holes in it is neither — demanding it here would turn a metal plate
#: into polka dots. What is meaningful — the jack of the first screen — is
#: 38 points across, carries a lit lamp and a written label, and its ink is
#: in the table above.
NOT_MEASURED = {
    ("rim", "plate"): "фаска в поле — материал, а не орган управления",
    ("ink-soft", "rim"): "мягких чернил над полем нет: 2.39, и потому нет",
    ("plate", "ground"): "плита и земля — две плоскости, а не текст на фоне",
}
for (ink, face), why in sorted(NOT_MEASURED.items()):
    got = ratio(values[ink], values[face]) if ink in values and face in values else 0
    check(f"пара {ink}/{face} не меряется: {why}", got > 1.0,
          "| значения пропали из tokens.css")
for ink, face, floor, what in PAIRS:
    if ink not in values or face not in values:
        check(f"пара {ink} на {face} объявлена", False, "| нет такого значения")
        continue
    got = ratio(values[ink], values[face])
    check(f"{what}: {ink} на {face} — {got:.2f} при нужных {floor}",
          got >= floor, "| пара не проходит порог")

# The loom runs behind the page and body text stands on top of it: a
# wire crosses a line of legend, and a signal crosses it brighter. These
# are not token pairs — each is a token laid over the ground at a
# strength written in the stylesheet — so the strength is read from the
# sheet rather than typed here. Changing it there re-measures the pair;
# typing it twice would let the two drift, which is the failure this
# whole table exists to prevent.
def over(top, under, alpha):
    """`top` laid on `under` at `alpha`, as the screen will show it."""
    one = [int(top[at:at + 2], 16) for at in (1, 3, 5)]
    two = [int(under[at:at + 2], 16) for at in (1, 3, 5)]
    return "#" + "".join("%02x" % round(alpha * a + (1 - alpha) * b)
                         for a, b in zip(one, two))


def strength(rule, what, per_cent):
    """What the stylesheet gives that layer, as a fraction of full."""
    found = re.search(rule, style, re.S)
    check(f"в оформлении сказано, какой «{what}»", found is not None,
          "| правило переписано, и пара перестала меряться")
    if not found:
        return 0.0
    return float(found.group(1)) / (100.0 if per_cent else 1.0)


LAYERS = [
    ("hair", "провод жгута",
     r"\.loom \{[^}]*?opacity:\s*([\d.]+)", False),
]

for token, what, rule, per_cent in LAYERS:
    alpha = strength(rule, what, per_cent)
    if not alpha:
        continue
    face = over(values[token], values["ground"], alpha)
    got = ratio(values["ink-soft"], face)
    check(f"легенды поверх «{what}» ({face}) — {got:.2f} при нужных 4.5",
          got >= 4.5, "| строку, которую пересекает жгут, читать труднее нормы")

# The faces the page loads are the faces the program ships. A page set in
# something the program does not have looks like the program and is not.
csproj = read(os.path.join(ROOT, "shell", "Rina.Shell", "Rina.Shell.csproj"))
for face in sorted(set(re.findall(r"fonts/([A-Za-z-]+\.ttf)", generated))):
    check(f"шрифт {face} есть и в оболочке", face in csproj,
          "| страница набрана тем, чего у программы нет")

# ---------------------------------------------------------------------------
# The promises made in public (`4.0b-C07`, `4.0b-D05`)
# ---------------------------------------------------------------------------
#
# The one about money is kept by being written down **before** there is a
# reason to break it, and on both pages: a promise made in one language is a
# promise made to half the readers.
print()
print("=== обещания, данные вслух ===")

SAID = {
    "русская": [
        ("Бета бесплатна", "бета бесплатна"),
        ("локальная база останется бесплатной",
         "локальная база останется бесплатной"),
        ("открытое остаётся открытым", "открытым остаётся"),
        ("телеметрии нет", "телеметрии нет"),
        ("страница без скриптов", "не выполняет скриптов"),
    ],
    "английская": [
        ("the beta is free", "the beta is free"),
        ("the local base stays free", "the local base stays free"),
        ("what stays open", "what stays open"),
        ("no telemetry", "there is no telemetry"),
        ("no scripts on the page", "runs no scripts"),
    ],
}
for where, promises in SAID.items():
    for what, phrase in promises:
        check(f"{where}: сказано — {what}", phrase.lower() in lower[where],
              "| обещание пропало со страницы")

# ---------------------------------------------------------------------------
# The download says what is true today
# ---------------------------------------------------------------------------
#
# The page must not offer a download that does not exist, and must not go on
# apologising once it does. Which of the two is true is asked of the tags,
# not of memory.
print()
print("=== скачивание ===")

NO_RELEASE = {
    "русская": "выпуска пока не было",
    "английская": "there has been no release yet",
}
try:
    tags = subprocess.run(["git", "tag", "--list", "4.*"], cwd=ROOT,
                          capture_output=True, text=True,
                          timeout=30).stdout.split()
    released = bool(tags)
    for where, phrase in NO_RELEASE.items():
        if released:
            check(f"{where}: оговорка снята — выпуск {tags[-1]} есть",
                  phrase not in lower[where],
                  "| выпуск вышел, а страница всё ещё извиняется")
            check(f"{where}: ведёт к файлу выпуска",
                  ".exe" in lower[where] or "/releases/" in lower[where],
                  "| выпуск есть, а скачать с неё нечего")
        else:
            check(f"{where}: сказано, что выпуска ещё нет",
                  phrase in lower[where],
                  "| кнопка обещает то, чего ещё нет")
            check(f"{where}: не обещает файла", ".exe" not in lower[where],
                  "| ссылка на установщик, которого не существует")
except (OSError, subprocess.TimeoutExpired) as trouble:
    check("git ответил, какие выпуски были", False, f"| {trouble}")

# ---------------------------------------------------------------------------
# The page is in the repository
# ---------------------------------------------------------------------------
#
# `/site` stood in `.gitignore` from the Python template — for mkdocs, which
# this project does not use. A page that exists only on the author's disk is
# published by nothing and checked by nobody.
print()
print("=== страница лежит в хранилище ===")

try:
    ignored = subprocess.run(["git", "check-ignore", "site/index.html"],
                             cwd=ROOT, capture_output=True, text=True,
                             timeout=30)
    check("site/ не исключена из хранилища", ignored.returncode != 0,
          "| .gitignore прячет страницу: её никто не опубликует")
except (OSError, subprocess.TimeoutExpired) as trouble:
    check("git ответил про .gitignore", False, f"| {trouble}")

print()
print("ИТОГО ошибок:", fails)
sys.exit(1 if fails else 0)
