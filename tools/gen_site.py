# -*- coding: utf-8 -*-
"""
Generating the product page's values from tokens.json (plan item `4.0b-D01`).

The page is a different medium from the program and, since the redesign, a
different world: the program is a flat instrument face, the page is a patch
field. Two things still must not be typed by hand: **the palette** and the
**files the page shows**.

A colour typed into a stylesheet is a second copy of the brand, and it
parts company with the first one silently — a page a shade off looks like a
page, not like a fault. The same goes for the screenshots: the page shows
the program, and a screenshot that stayed behind shows a program that no
longer exists. That has already happened here once.

So: the values are generated, the files are copied, and `--check` says
whether either has drifted.

**The page's world is its own; its colours are not.** Everything on the page
is derived from the `graphite` finish — the ink, the signal, the live lamp,
the seam — and only the ground beneath it is the page's own value, because
the program has no room lit that dimly. A cord the colour of the program's
accent is the same promise in another material; a cord in a colour picked
here would be a second brand.

**The page is dark and has no light rendition.** Not a category habit: the
world is a dim exchange room with lit lamps, and a light one would put the
lamps out. The reader who prefers light gets a page that ignores the
preference rather than a page that contradicts itself.

To run:
    python tools/gen_site.py            write
    python tools/gen_site.py --check    compare without rewriting
"""

import json
import posixpath
import re
from html import escape
import os
import shutil
import sys

import nebula

from console import use_utf8

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOKENS = os.path.join(ROOT, "docs", "design", "tokens.json")
SITE = os.path.join(ROOT, "site")
GENERATED = os.path.join(SITE, "tokens.css")
REPO = "https://github.com/Luna-coreX/RinaAssistant"
BLOB = REPO + "/blob/HEAD/"
PORTAL = "https://neurosync-foundry-portal.pages.dev/"
LOOM = os.path.join(SITE, "wires.svg")
MOCK = os.path.join(SITE, "mock", "cases.js")
FINISHES = os.path.join(SITE, "mock", "finishes.css")
RAMPS = os.path.join(SITE, "mock", "flow-ramps.js")

#: The finish the page borrows from. The darkest of the three, because the
#: page is lit like the room the world lives in.
FINISH = "graphite"

#: The faces the page loads, and the weight each stands for.
#:
#: A subset of what the shell ships (`Rina.Shell.csproj`): the page uses
#: five of the twelve, and carrying the rest would mean a megabyte of fonts
#: nobody displays. Every one of these is in the shell's list —
#: `check_site.py` holds that, so the page cannot quietly acquire a face the
#: program does not have.
FACES = [
    ("Unbounded", "Unbounded-Regular.ttf", 400),
    ("Unbounded", "Unbounded-Medium.ttf", 500),
    ("Onest", "Onest-Regular.ttf", 400),
    ("Onest", "Onest-Medium.ttf", 500),
    ("Geologica", "Geologica-Regular.ttf", 400),
    ("Geologica", "Geologica-Medium.ttf", 500),
]

def copies():
    """What is copied into `site/`, as destination -> source.

    Cloudflare Pages serves one directory and nothing above it, so the
    page cannot point at `assets/`, where the fonts and the mark live. The
    copy is therefore unavoidable; what is avoidable is the copy drifting,
    and that is what `--check` is for.

    Screenshots are not among the copies. The ones that were here showed
    an interface two releases old, and the page is getting a working
    mock-up of the program instead.
    """
    out = {}
    for family, name, _ in FACES:
        out["fonts/" + name] = os.path.join(ROOT, "assets", "fonts",
                                            family, name)
    out["logo.png"] = os.path.join(ROOT, "assets", "logo.png")
    out["favicon.ico"] = os.path.join(ROOT, "assets", "icon.ico")
    return out


def palette(finish):
    """The page's colours, all but one of them the program's.

    The names are the world's — ground, plate, hole, cord, lamp — because
    that is what the stylesheet reaches for; what stands behind each of them
    is written here once.
    """
    color = finish["color"]
    return [
        ("ground", nebula.mix(color["GLASS"], "#000000", 0.45),
         "комната коммутаторной: единственное значение страницы"),
        ("plate", color["FACE"], "плита, в которой просверлено поле"),
        ("plate-low", color["FACE_LOW"], "плита под нажатием"),
        ("hole", nebula.mix(color["FACE_SUNK"], "#000000", 0.55),
         "нутро гнезда"),
        ("rim", nebula.mix(color["FACE"], color["INK"], 0.34),
         "фаска гнезда — единственное, что его выдаёт"),
        ("hair", color["SEAM"], "волосяная линия"),
        ("ink", color["INK"], "чернила"),
        ("ink-soft", color["INK_SOFT"], "легенды"),
        ("ink-faint", color["INK_FAINT"], "выключенное"),
        ("cord", color["SIGNAL"], "шнур и единственный акцент"),
        ("cord-sunk", color["SIGNAL_SUNK"], "шнур под нажатием"),
        ("lamp", color["LIVE"], "лампа занятой линии"),
        ("strip", color["INK"], "наборная этикетка: плашка"),
        ("strip-ink", color["FACE"], "наборная этикетка: буквы"),
    ]


#: The wires of the loom: where each one stands and how far it swings.
#:
#: In pairs and unevenly — an equal step reads as column rules rather
#: than as a loom. Two wires are set further back: without a difference
#: in weight, six lines look like a grid. The tile is wider than an
#: ordinary window, so it does not repeat sideways and the drawing does
#: not read as wallpaper.
LOOM_TILE = (2400, 1400)
LOOM_WIRES = [
    (150, 320, 1.6, 1.0),
    (320, 290, 1.6, 1.0),
    (760, 260, 1.6, 1.0),
    (1180, -280, 1.1, 0.55),
    (1490, 290, 1.6, 1.0),
    (1660, 270, 1.6, 1.0),
    (2050, -240, 1.1, 0.55),
    (2320, 280, 1.6, 1.0),
]


def wires(tokens):
    """The tile that lies under the page, in the colour of a hairline.

    Generated rather than written by hand for one reason: the colour.
    A `#383d41` typed into an SVG would be a second copy of the brand in
    a file nobody opens, and it would go on being the old colour for as
    long as it took somebody to notice.

    The tile meets itself top to bottom: each wire is one full wave, and
    its control points are mirrored (x+a at a quarter, x-a at three
    quarters), so it leaves the bottom edge at the same place and the
    same angle it entered the top. `background-repeat: repeat-y` then
    shows no seam.
    """
    wide, tall = LOOM_TILE
    hair = tokens["finishes"][FINISH]["color"]["SEAM"]
    out = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 '
        + str(wide) + " " + str(tall) + '" width="' + str(wide)
        + '" height="' + str(tall) + '">',
        "<!-- Порождено tools/gen_site.py по docs/design/tokens.json.",
        "     Руками не править: правка переживёт до следующего запуска.",
        "",
        "     Изнанка панели — жгут проводов под страницей. Плитка",
        "     сходится сама с собой по вертикали и повторяется только",
        "     вниз; цвет — волосяная линия отделки. -->",
        '<g fill="none" stroke="' + hair + '" stroke-linecap="round">',
    ]
    for base, sway, width, fade in LOOM_WIRES:
        out.append(
            '  <path d="M %d 0 C %d %d, %d %d, %d %d" stroke-width="%s"%s/>'
            % (base, base + sway, tall // 4, base - sway, tall * 3 // 4,
               base, tall, width,
               "" if fade >= 1 else ' opacity="%s"' % fade))
    out += ["</g>", "</svg>", ""]
    return "\n".join(out)


#: The documents the site publishes: slug, source, title, one line,
#: language.
#:
#: Eleven documents, and the list is the contract: `check_site.py` asks
#: that every one of them has a page and that the page is linked from
#: the landing. A document added to the repository and not to this list
#: simply is not published — which is a decision, and has to be made
#: rather than happen.
#:
#: The language is the document's own. Four of them are written in
#: English and seven in Russian, and pretending otherwise — a Russian
#: title over an English text — would be worse than saying so.
PAPERS = [
    ("readme", "README.md", "README",
     "Что это, как поставить, что внутри.", "en"),
    ("architecture", "docs/ARCHITECTURE.md", "Архитектура",
     "Два процесса, протокол между ними, кто что решает.", "ru"),
    ("plugins", "docs/plugins/WRITING-PLUGINS.md", "Как писать плагины",
     "Подробное руководство; краткая опора — на странице API.", "ru"),
    ("design", "docs/design/SYSTEM.md", "Дизайн-система",
     "Отделки, цвет, типографика, движение — со значениями.", "ru"),
    ("security", "SECURITY.md", "Безопасность",
     "Границы доверия и куда нести уязвимость.", "en"),
    ("threats", "docs/security/THREAT-MODEL.md", "Модель угроз",
     "Поверхности, угрозы, остаточный риск.", "ru"),
    ("debugging", "docs/DEBUGGING.md", "Отладка",
     "Как отлаживать две программы сразу.", "ru"),
    ("contributing", "CONTRIBUTING.md", "Участие",
     "Как прислать правку; соглашение подписывать не нужно.", "en"),
    ("triage", "docs/TRIAGE.md", "Разбор входящего",
     "Кто читает, в какой срок и какие четыре исхода.", "ru"),
    ("changelog", "CHANGELOG.md", "Что менялось",
     "По выпускам.", "en"),
    ("plan", "docs/ROADMAP.md", "Полный план",
     "Рубежи, блоки и все задачи: размер, зависимости, состояние.", "ru"),
]

#: Task lines of the plan: `**4.0-I01 · Сборка** — L — всё — **ВЫПОЛНЕНО**`.
TASK = re.compile(r"^\*\*((?:4\.0|5\.0|V)[\w.+-]*)\s*·\s*([^*]+)\*\*(.*)$")
STAGE = re.compile(r"^#\s+(?:РУБЕЖ|ВЕРСИЯ|ТРЕК)\s+(.+)$")


def address(target, here):
    """Where a link inside a published document should point.

    The documents link to each other and to files that have no page.
    The first kind becomes a local address, the second goes to the
    repository. A link left alone would be a 404 on the site — the
    ordinary way a published document quietly stops being usable.
    """
    # The site's own address, met inside a document, is this page: a
    # reader sent out to the site they are already reading is the
    # smallest possible kind of broken link, and the honest fix is not
    # to allow the host but to stop leaving.
    if target.rstrip("/") in (PORTAL.rstrip("/"),):
        return "/"
    if target.startswith(("http://", "https://", "#", "mailto:")):
        return target
    body, _, anchor = target.partition("#")
    anchor = "#" + anchor if anchor else ""
    if not body:
        return anchor
    path = posixpath.normpath(
        posixpath.join(posixpath.dirname(here), body))
    for slug, source, _title, _lead, _lang in PAPERS:
        if source == path:
            return "/docs/" + slug + "/" + anchor
    return BLOB + path + anchor


def folded(task, said):
    """One task, and the paragraph that says what it is, folded away.

    `said` is everything the document wrote under the task; what comes
    back is the task line and, behind a disclosure, its first
    paragraph. A task with nothing under it is just the line — an
    empty disclosure is an affordance that lies.
    """
    if not task:
        return []
    first = []
    for line in said:
        if not line.strip():
            if first:
                break
            continue
        first.append(line)
    if not first:
        return ["", task, ""]
    return ["", "::details", "::summary " + task, ""] + first + ["", "::end", ""]


def plain(source):
    """The plan without the workshop around it.

    `ROADMAP.md` is written for whoever is building the thing: every
    task carries the argument behind it, the edition that did not work,
    the measurement that settled it. Four thousand lines of that is the
    right amount in the repository and the wrong amount on a product
    page — seven hundred kilobytes against fifteen for every other
    document here. A reader who came to see what is planned was handed
    a notebook.

    So the page keeps what a plan is: the milestone, the block, what
    the block is for, and every task with its size, its dependencies,
    its state — and, behind a disclosure, the paragraph that says what
    the task actually is. What goes is everything after that first
    paragraph, and the headings the workshop grows inside a block —
    `Поправка`, `Четвёртая редакция`, `Сделано`.

    The first paragraph is the cut because the document is written that
    way: it states the task, and the argument comes after it under its
    own bold lead. `4.0-I01` opens with the decision and the three
    files that carry it, and then spends two screens on the installer
    that lied on its first run.

    The rule is the document's own shape rather than a list of
    exceptions, which would go stale the first time a block is added:
    text before the first task of a section says what the section is
    for and stays; text after a task belongs to that task. A task is
    kept wherever it is found, including under a heading that is itself
    dropped — `4.0b-A06` lives under `Обязательный список беты`, and
    the task is not the heading's to take with it.
    """
    out = []
    lines = source.replace("\r\n", "\n").split("\n")
    seen = False
    fenced = False
    said = []
    for line in lines:
        # A `#` inside a fence is a shell comment, and dropping one
        # would be a silent hole in a code block rather than a visible
        # one. There are none in the plan today; the reason to handle
        # it is that there is no way to notice the day there are.
        if line.startswith("```"):
            fenced = not fenced
            (out if not seen else said).append(line)
            continue
        if fenced:
            (out if not seen else said).append(line)
            continue
        if TASK.match(line):
            out.extend(folded(seen, said))
            seen = line
            said = []
            continue
        if re.match(r"^-{3,}\s*$", line):
            # A rule closes the block, so it closes the task under it
            # too. Left inside, it was the whole of three disclosures:
            # `4.0-U14`, `5.0-C06` and `V-09` are each the last task of
            # their block and have no paragraph of their own.
            out.extend(folded(seen, said))
            seen = False
            said = []
            out.append(line)
            continue
        if re.match(r"^#{3,}\s", line):
            continue
        if line.startswith("#"):
            out.extend(folded(seen, said))
            seen = False
            said = []
            out.append(line)
            continue
        if seen:
            said.append(line)
        else:
            out.append(line)
    out.extend(folded(seen, said))

    # Dropped paragraphs leave runs of blank lines behind, and the
    # reader would parse those into empty paragraphs and stray rules.
    tight = []
    for line in out:
        if not line.strip() and tight and not tight[-1].strip():
            continue
        if re.match(r"^-{3,}\s*$", line) and (not tight or tight[-1].startswith("#")):
            continue
        tight.append(line)
    return "\n".join(tight)


#: What a milestone is called on the page, where the plan's own heading
#: is not the name a reader needs.
STAGE_NAMES = {"V": "голос"}

#: Milestones run in time, not in the order the document first
#: mentions one: the update block sits inside the port, and without
#: this `4.0-stable` stood on the strip ahead of the beta.
STAGE_ORDER = ["4.0-port", "4.0-beta", "4.0-stable", "4.1+", "5.0.0"]


def counted(source):
    """How many tasks of each milestone are done.

    The milestone of a task is taken from `docs/scope-4.0.json`, not
    from the heading it stands under: the update block lives under
    `РУБЕЖ 4.0-port` and half of it belongs to `4.0-stable`. Counting
    by heading gave «102 из 111» for a milestone that is closed at 100
    of 100 — a wrong number in the one place the page is asking to be
    believed. What the snapshot does not know about is counted by its
    heading, which is the honest fallback.
    """
    with open(os.path.join(ROOT, "docs", "scope-4.0.json"),
              encoding="utf-8") as handle:
        scope = json.load(handle)

    order = []
    tally = {}
    stage = None
    for line in source.split("\n"):
        found = STAGE.match(line)
        if found:
            stage = found.group(1).split("—")[0].strip()
            stage = STAGE_NAMES.get(stage, stage)
            continue
        found = TASK.match(line)
        if not found:
            continue
        where = scope.get(found.group(1), {}).get("milestone") or stage
        if where is None:
            continue
        if where not in tally:
            order.append(where)
            tally[where] = [0, 0]
        tally[where][1] += 1
        if "ВЫПОЛНЕНО" in found.group(3):
            tally[where][0] += 1
    order.sort(key=lambda one: (STAGE_ORDER.index(one)
                               if one in STAGE_ORDER else len(STAGE_ORDER)))
    return [(one, tally[one][0], tally[one][1]) for one in order]


def paper(slug, title, lead, lang, source, tokens):
    """One published document, as the page the site shows."""
    import markdown_site

    with open(os.path.join(ROOT, source.replace("/", os.sep)),
              encoding="utf-8") as handle:
        text = handle.read()
    strip = ""
    if slug == "plan":
        rows = counted(text)
        strip = ("    <div class=\"strip\">\n"
                 + "".join('      <div><b>%d/%d</b><span>%s</span></div>\n'
                           % (done, all_, escape(name))
                           for name, done, all_ in rows)
                 + "    </div>\n")
        text = plain(text)
    body, contents = markdown_site.render(
        text, lambda one: address(one, source))

    rail = "".join('      <li><a href="#%s">%s</a></li>\n' % (name, shown)
                   for name, shown in contents)
    tongue = "ru" if lang == "ru" else "en"
    said = ("Документ репозитория, страницей."
            if lang == "ru" else
            "Документ репозитория, страницей. Написан по-английски.")
    # The plan is the one page that is not the whole document, and a
    # page that quietly shows less than it claims is worse than a long
    # page. It says what it left out and where that went.
    if slug == "plan":
        said = ("Документ репозитория, страницей — в сокращении: "
                "разбор каждой задачи остался в источнике.")
        whole = ("; здесь — рубежи, блоки и задачи, "
                 "а доводы, редакции и замеры по каждой — там.")
    else:
        whole = ("; страница порождается из него "
                 "и расходиться с ним не может.")

    return """<!DOCTYPE html>
<html lang="{tongue}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} — Rina Assistant</title>
<meta name="description" content="{lead}">
<link rel="icon" href="../../favicon.ico" sizes="any">
<meta property="og:type" content="article">
<meta property="og:title" content="{title} — Rina Assistant">
<meta property="og:description" content="{lead}">
<meta property="og:image" content="../../logo.png">
<meta name="twitter:card" content="summary_large_image">
<link rel="stylesheet" href="../../tokens.css">
<link rel="stylesheet" href="../../style.css">
</head>
<body class="doc-page">
<!-- Порождено tools/gen_site.py по {source}. Руками не править. -->

<div class="loom" aria-hidden="true"></div>

<a class="skip" href="#content">К содержимому</a>

<header class="rail">
  <div class="frame rail-in">
    <a class="mark" href="/"><img src="../../logo.png" alt="" width="24" height="24">Rina Assistant</a>
    <nav>
      <a href="/#capabilities">Возможности</a>
      <a href="/#privacy">Приватность</a>
      <a href="/#docs">Документация</a>
      <a href="/api/">Разработчику</a>
    </nav>
  </div>
  <div class="progress"></div>
</header>

<section class="hero field" id="value">
  <div class="frame">
    <div class="hero-say">
      <h1>{title}</h1>
      <p class="lead">{lead}</p>
      <p class="note">{said} Источник — <a href="{blob}{source}">{source}</a>{whole}</p>
    </div>
{strip}  </div>
</section>

<div class="frame doc">
  <nav class="doc-rail" aria-label="Разделы">
    <ol>
{rail}    </ol>
  </nav>

  <main class="doc-body paper" id="content">
{body}
  </main>
</div>

<footer class="frame">
  <span>Apache-2.0 · NeuroSync Foundry</span>
  <nav>
    <a href="/">Главная</a>
    <a href="/#docs">Все документы</a>
    <a href="{blob}{source}">Источник</a>
    <a href="{repo}">Хранилище</a>
  </nav>
</footer>

</body>
</html>
""".format(tongue=tongue, title=escape(title), lead=escape(lead),
           said=said, whole=whole, source=source, blob=BLOB, repo=REPO,
           strip=strip, rail=rail, body=body)


def papers(tokens):
    """Every published document, by the file it becomes."""
    return {"docs/%s/index.html" % slug:
            paper(slug, title, lead, lang, source, tokens)
            for slug, source, title, lead, lang in PAPERS}


#: What the mock says it did, by the intent the recorded set gives it.
#:
#: The golden set (`docs/golden/utterances.json`) pins **what she
#: understood** — the intent and its arguments — and pins it by running
#: the real parser. It does not pin the words she answers with, so those
#: words are the mock's own, and the page says so outright. Everything
#: to the left of the answer is the program's recorded behaviour.
#:
#: `check_site.py` asks that this table covers every intent in the set
#: and invents none: a new intent recorded in the golden set must be
#: answered here before the mock can be built.
MOCK_SAID = {
    "app.launch": ("сделала", "Открываю {app}."),
    "app.not_found": ("не нашла", "Такой программы в указателе нет."),
    "alias.teach": ("запомнила", "«{word}» — это {app}. Запомнила."),
    "alias.ambiguous": ("переспросила",
                        "Под «{word}» подходит несколько: {options}. Какую?"),
    "alias.unknown": ("не нашла",
                      "«{query}» я не нашла — запоминать нечего."),
    "ask.wake": ("слушает", "Да?"),
    "builtin.answer": ("ответила", "{topic}"),
    "calc": ("посчитала", "{result}"),
    "calc.zero_division": ("отказалась", "На ноль не делится."),
    "cancelled": ("отменила", "Хорошо, отменила."),
    "fallback.none": ("не поняла",
                      "Не узнала фразу, а искать в сети сейчас не буду."),
    "fallback.search": ("переспросила", "Не узнала фразу. Поискать в сети?"),
    "reminder.create": ("поставила", "{kind} поставлен{tail}."),
    "reminder.list": ("ответила", "Пока ничего не заведено."),
    "reminder.cancel": ("отменила", "Отменила всё, что было заведено."),
    "reminder.ambiguous": ("переспросила",
                           "Программ с таким именем несколько: {options}."),
    "reminder.unknown_app": ("не нашла",
                             "К такой программе привязать нечего."),
    "silence": ("промолчала", ""),
    "system.action": ("сделала", "{action}"),
    "system.confirm": ("переспросила", "{action} — это необратимо. Точно?"),
    "websearch": ("ищет", "Ищу: {query}."),
}

#: Words for what the program names in English inside its own data.
MOCK_WORDS = {
    "volume_up": "Прибавила громкость",
    "volume_down": "Убавила громкость",
    "volume_mute": "Выключила звук",
    "media_next": "Следующий трек",
    "media_prev": "Предыдущий трек",
    "media_play_pause": "Пауза",
    "lock": "Заблокировала рабочий стол",
    "screenshot": "Сняла экран",
    "sleep": "Усыпить компьютер",
    "restart": "Перезагрузить компьютер",
    "shutdown": "Выключить компьютер",
    "timer": "Таймер",
    "alarm": "Будильник",
    "reminder": "Напоминание",
    "name": "Меня зовут Рина.",
    "capabilities": "Открываю программы, ставлю таймеры, считаю, "
                    "управляю системой.",
    "thanks": "Пожалуйста.",
}

#: Which actions are irreversible: the mock shows them the way the
#: program does — a question with hatching, not a done deed.
MOCK_HEAVY = ("shutdown", "restart", "sleep")

#: The phrases offered as chips, by their id in the recorded set.
#:
#: Chosen to walk the reader through the shapes the answer can take:
#: done, asked, refused, counted, silent. Ids rather than text, so a
#: reworded phrase in the set either follows or turns the check red.
MOCK_CHIPS = [
    "app.launch.plain.2",
    "reminder.timer.1",
    "calc.mul.2",
    "system.volume.up.1",
    "system.confirm.shutdown",
    "alias.teach.rule",
    "builtin.name.1",
]


def mock_cases():
    """The recorded set, as the mock's data."""
    with open(os.path.join(ROOT, "docs", "golden", "utterances.json"),
              encoding="utf-8") as handle:
        cases = json.load(handle)["cases"]

    out = []
    for one in cases:
        want = dict(one["expect"])
        intent = want.pop("intent", None)
        if intent not in MOCK_SAID:
            continue
        note = want.pop("note", "")
        state, shape = MOCK_SAID[intent]
        said = shape
        if "{topic}" in shape:
            said = MOCK_WORDS.get(want.get("topic"), "")
        if "{action}" in shape:
            said = shape.replace("{action}",
                                 MOCK_WORDS.get(want.get("action"), ""))
        if "{kind}" in shape:
            kind = want.get("kind")
            said = shape.replace("{kind}", MOCK_WORDS.get(kind, "Напоминание"))
            said = said.replace("{tail}", "о" if kind == "reminder" else "")
        for field in ("app", "word", "query", "result"):
            if "{%s}" % field in said:
                said = said.replace("{%s}" % field, str(want.get(field, "")))
        if "{options}" in said:
            said = said.replace("{options}",
                                ", ".join(want.get("options", [])))
        out.append({
            "id": one["id"],
            "say": one["say"],
            "intent": intent,
            "args": {k: v for k, v in want.items() if k != "options"},
            "state": state,
            "said": said,
            "heavy": want.get("action") in MOCK_HEAVY,
            # The set's own note on why the same words mean
            # something else here. One phrase is recorded several
            # times: "выключи компьютер" without the wake word is
            # silence, not a shutdown.
            "note": note,
        })

    chips = [one for one in MOCK_CHIPS
             if any(case["id"] == one for case in out)]
    head = [
        "/* Порождено tools/gen_site.py по docs/golden/utterances.json.",
        " * Руками не править.",
        " *",
        " * Это записанные фразы программы — те же, которыми закреплён",
        " * её разбор. Макет ничего не выдумывает: он показывает то,",
        " * что по этой фразе поняла настоящая Рина. */",
        "",
    ]
    return "\n".join(head + [
        "window.RINA_CASES = "
        + json.dumps(out, ensure_ascii=False, indent=1) + ";",
        "window.RINA_CHIPS = "
        + json.dumps(chips, ensure_ascii=False) + ";",
        "",
    ])


def finishes(tokens):
    """The program's own values, for the window the mock-up draws.

    Not the page's palette. The page borrows from the graphite finish
    and renames as it borrows — `plate`, `hole`, `cord` — because it is
    a switchboard and not an instrument face. The mock-up is the
    instrument face, so it takes the names the program uses and the
    values behind them, all three finishes and every accent, and the
    glass densities besides: the top bar and the section column hold
    zero, everything a person presses is glass.

    Written out rather than borrowed for the same reason the palette is
    generated at all. A window drawn in approximately the program's
    colours is a drawing of a program that does not exist.
    """
    out = [
        "/* Порождено tools/gen_site.py по docs/design/tokens.json.",
        " * Руками не править.",
        " *",
        " * Значения программы для окна макета: три отделки, каждая",
        " * со своей лестницей поверхностей и чернил, и плотности",
        " * стекла. Имена — те же, что в `tokens.json`.",
        " */",
        "",
    ]

    glass = tokens["glasswork"]
    out.append(":root {")
    for name, value in sorted(glass.items()):
        if name == "note":
            continue
        out.append("  --glass-%s: %s;" % (name, value))
    out += ["}", ""]

    for name in ("silver", "black", "graphite"):
        finish = tokens["finishes"][name]
        color = finish["color"]
        out.append(".win.%s {" % name)
        for role in ("FACE", "FACE_HIGH", "FACE_LOW", "FACE_SUNK", "SEAM",
                     "GLASS", "GLASS_TEXT", "GLASS_DIM", "INK", "INK_SOFT",
                     "INK_FAINT", "SIGNAL", "SIGNAL_SUNK", "HATCH", "LIVE"):
            out.append("  --%s: %s;" % (role.lower().replace("_", "-"),
                                        color[role]))
        out += ["}", ""]

        for accent, stops in finish["accents"].items():
            out.append(".win.%s.%s {" % (name, accent))
            out.append("  --signal: %s;" % stops["signal"])
            out.append("  --signal-sunk: %s;" % stops["signal_sunk"])
            out += ["}", ""]

    return "\n".join(out)


def ramps(tokens):
    """The flow's palettes and its numbers, for the mock-up.

    The living background is the same arithmetic in the program and on
    the page (`site/mock/flow.js` is a port of `Flow.cs`), and the one
    thing a port must not carry is the palette: those are computed by
    `tools/nebula.py` from the finish and the accent, and a second
    implementation of that is exactly what `nebula.py` exists to
    prevent. So they are generated here, all of them — three finishes
    by six accents, vivid and calm — together with the numbers the
    field is drawn with.
    """
    out = {}
    for name, finish in tokens["finishes"].items():
        flow = finish["nebula"]
        shades = nebula.every_ramp(finish)
        accents = sorted({one.split("/")[0] for one in shades})
        out[name] = {
            "scale": flow["scale"],
            "warp": flow["warp"],
            "period": tokens["motion"]["background"]["period"],
            "drift": tokens["motion"]["background"]["drift"],
            "accents": {
                one: {
                    "vivid": shades[one],
                    "calm": next(stops for key, stops in shades.items()
                                 if key.startswith(one + "/")),
                }
                for one in accents
            },
        }
    head = [
        "/* Порождено tools/gen_site.py по docs/design/tokens.json.",
        " * Руками не править.",
        " *",
        " * Палитры живого фона: три отделки на шесть акцентов, яркая и",
        " * приглушённая. Считает их tools/nebula.py — тот же модуль, что",
        " * и для программы, и это единственное место, где они считаются.",
        " * Рядом значения, которыми поле рисуется. */",
        "",
    ]
    return "\n".join(head + [
        "window.RINA_FLOW = "
        + json.dumps(out, ensure_ascii=False, indent=1) + ";",
        "",
    ])


def css(tokens):
    """The whole generated stylesheet."""
    roles = tokens["typography"]["role"]
    families = tokens["typography"]["family"]
    finish = tokens["finishes"][FINISH]

    out = [
        "/* Порождено tools/gen_site.py по docs/design/tokens.json.",
        " * Руками не править: правка переживёт ровно до следующего запуска,",
        " * а расхождение с программой переживёт дольше.",
        " *",
        " * Мир страницы — коммутационное поле; цвета — отделки «"
        + finish["title"] + "».",
        " * Своё у страницы одно значение: земля, на которой всё стоит. */",
        "",
    ]

    for family, name, weight in FACES:
        out += [
            "@font-face {",
            "  font-family: '" + family + "';",
            "  src: url('fonts/" + name + "') format('truetype');",
            "  font-weight: " + str(weight) + ";",
            "  font-style: normal;",
            "  font-display: swap;",
            "}",
        ]
    out.append("")

    out.append(":root {")
    out.append("  color-scheme: dark;")
    out.append("")
    out.append("  /* Гарнитуры: наборная, текстовая, показаний. */")
    out.append("  --font-display: '" + families["display"]
               + "', system-ui, sans-serif;")
    out.append("  --font-ui: '" + families["ui"] + "', system-ui, sans-serif;")
    out.append("  --font-figure: '" + families["figure"]
               + "', system-ui, sans-serif;")
    out.append("")
    out.append("  /* Кегли ролей прибора. Страница читает их с поправкой:"
               " --scale в style.css. */")
    for role, spec in roles.items():
        out.append("  --type-" + role + ": " + str(spec["size"]) + "px;")
    out.append("")
    out.append("  /* Лестница просветов. */")
    for step, value in tokens["space"].items():
        out.append("  --space-" + step + ": " + str(value) + "px;")
    out.append("")
    out.append("  /* Радиусы: у прибора углы тугие. */")
    for step, value in tokens["radius"].items():
        out.append("  --radius-" + step + ": " + str(value) + "px;")
    out.append("")
    out.append("  /* Длительности и смягчение. */")
    for step, value in tokens["motion"].items():
        if isinstance(value, (int, float)):
            out.append("  --motion-" + step + ": " + str(value) + "ms;")
    for name, curve in tokens["motion"]["easing"].items():
        out.append("  --ease-" + name + ": " + curve + ";")
    out.append("")
    out.append("  /* Штриховка необратимого: единственный его признак. */")
    hatch = tokens["hatch"]
    out.append("  --hatch-angle: " + str(hatch["angle"]) + "deg;")
    out.append("  --hatch-line: " + str(hatch["line"]) + "px;")
    out.append("  --hatch-gap: " + str(hatch["gap"]) + "px;")
    out.append("  --hatch-opacity: " + str(hatch["opacity"]) + ";")
    out.append("")
    out.append("  /* Коммутационное поле. */")
    for name, value, why in palette(finish):
        out.append("  --" + name + ": " + value + ";  /* " + why + " */")
    out.append("}")
    out.append("")
    return "\n".join(out)


def same(one, two):
    """Byte for byte.

    A screenshot differing by a pixel is a screenshot of a different
    program, and there is no tolerance here worth having.
    """
    with open(one, "rb") as first, open(two, "rb") as second:
        return first.read() == second.read()


def main(argv):
    use_utf8()
    with open(TOKENS, encoding="utf-8") as handle:
        tokens = json.load(handle)
    wanted = css(tokens)
    drawn = wires(tokens)
    written = papers(tokens)
    written[os.path.relpath(MOCK, SITE).replace(os.sep, "/")] = mock_cases()
    written[os.path.relpath(FINISHES, SITE).replace(os.sep, "/")] = \
        finishes(tokens)
    written[os.path.relpath(RAMPS, SITE).replace(os.sep, "/")] = ramps(tokens)
    files = copies()

    missing = [src for src in files.values() if not os.path.isfile(src)]
    if missing:
        for src in missing:
            print("нет исходного файла:", os.path.relpath(src, ROOT))
        return 1

    if "--check" in argv:
        if not os.path.isfile(GENERATED):
            print("нет порождённого файла: site/tokens.css")
            print("Перезапустите: python tools/gen_site.py")
            return 1
        with open(GENERATED, encoding="utf-8") as handle:
            if handle.read() != wanted:
                print("site/tokens.css разошёлся с tokens.json")
                print("Перезапустите: python tools/gen_site.py")
                return 1
        if not os.path.isfile(LOOM):
            print("нет порождённого файла: site/wires.svg")
            print("Перезапустите: python tools/gen_site.py")
            return 1
        with open(LOOM, encoding="utf-8") as handle:
            if handle.read() != drawn:
                print("site/wires.svg разошёлся с tokens.json")
                print("Перезапустите: python tools/gen_site.py")
                return 1
        for dest, page in sorted(written.items()):
            path = os.path.join(SITE, dest.replace("/", os.sep))
            if not os.path.isfile(path):
                print("нет порождённой страницы: site/" + dest)
                print("Перезапустите: python tools/gen_site.py")
                return 1
            with open(path, encoding="utf-8") as handle:
                if handle.read() != page:
                    print("site/" + dest + " разошёлся с документом")
                    print("Перезапустите: python tools/gen_site.py")
                    return 1
        for dest, src in sorted(files.items()):
            path = os.path.join(SITE, dest.replace("/", os.sep))
            if not os.path.isfile(path):
                print("site/" + dest + " не скопирован")
                print("Перезапустите: python tools/gen_site.py")
                return 1
            if not same(path, src):
                print("site/" + dest + " разошёлся с "
                      + os.path.relpath(src, ROOT))
                print("Перезапустите: python tools/gen_site.py")
                return 1
        print("страница сходится с tokens.json, с документами и "
              "с исходными файлами (" + str(len(files) + len(written))
              + " файла)")
        return 0

    os.makedirs(SITE, exist_ok=True)
    with open(GENERATED, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(wanted)
    with open(LOOM, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(drawn)
    for dest, page in sorted(written.items()):
        path = os.path.join(SITE, dest.replace("/", os.sep))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(page)
    for dest, src in sorted(files.items()):
        path = os.path.join(SITE, dest.replace("/", os.sep))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        shutil.copyfile(src, path)
    print("порождено: site/tokens.css, site/wires.svg")
    print("  страниц документов и данных макета: " + str(len(written)))
    print("  скопировано файлов: " + str(len(files))
          + " (шрифтов " + str(len(FACES)) + ")")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
