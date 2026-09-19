# -*- coding: utf-8 -*-
"""Markdown of this repository -> markup of this site.

**A subset, and a chosen one.** Not a Markdown library: the project adds
no dependencies, and a general renderer would bring a hundred things
these documents never use, together with the job of keeping its output
inside the page's own type scale. What the documents do use was counted
first (`tools/gen_site.py` publishes eleven of them): headings, lists,
tables, fenced code, quotes, rules, and the four inline forms. Anything
outside that list is passed through as text rather than guessed at.

**The output is the page's markup, not generic HTML.** A list comes out
as `ul.plain`, a note as `p.note` — the same classes the hand-written
pages use, so a published document looks like part of the site and not
like a document someone pasted into it.

**Links are rewritten, and this is the part that matters.** A document
in the repository points at other files in the repository. On the site
some of those have a page and most do not, so the caller decides for
each target: the published ones become local addresses, the rest go to
the repository. A link that silently became a 404 would be the ordinary
way this whole idea fails.
"""

import html
import re

#: Inline code is taken out of the text before anything else is done to
#: it and put back at the very end. Otherwise `**` inside a code span
#: becomes bold, and the document loses the thing it was showing.
#: A sentinel that cannot occur in a document and survives
#: `html.escape` untouched: the escaping happens between taking the
#: code spans out and putting them back.
KEPT = "⸤code:%d⸥"

FENCE = re.compile(r"^```+\s*([\w+-]*)\s*$")
HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
RULE = re.compile(r"^\s*(-{3,}|\*{3,}|_{3,})\s*$")
BULLET = re.compile(r"^\s*[-*]\s+(.*)$")
NUMBER = re.compile(r"^\s*\d+[.)]\s+(.*)$")
QUOTE = re.compile(r"^>\s?(.*)$")
ROW = re.compile(r"^\s*\|(.+)\|\s*$")
SPLIT = re.compile(r"^\s*\|[\s:|-]+\|\s*$")
TAG = re.compile(r"<[^>]+>")

CODE = re.compile(r"`([^`]+)`")
LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
BOLD = re.compile(r"\*\*([^*]+)\*\*")
ITALIC = re.compile(r"(?<![\w*])\*([^*\n]+)\*(?![\w*])")
BARE = re.compile(r"(?<![\"'=(>])\bhttps?://[^\s<>()\[\]\"']+")


def slug(title, taken):
    """An anchor for a heading: readable, latin, and never repeated."""
    LATIN = {
        "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e",
        "ё": "e", "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k",
        "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r",
        "с": "s", "т": "t", "у": "u", "ф": "f", "х": "h", "ц": "c",
        "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "", "ы": "y", "ь": "",
        "э": "e", "ю": "yu", "я": "ya",
    }
    plain = TAG.sub("", title).lower()
    out = []
    for one in plain:
        if one in LATIN:
            out.append(LATIN[one])
        elif one.isalnum():
            out.append(one)
        elif out and out[-1] != "-":
            out.append("-")
    name = "".join(out).strip("-") or "section"
    if name in taken:
        taken[name] += 1
        name = f"{name}-{taken[name]}"
    else:
        taken[name] = 1
    return name


def inline(text, link, kept):
    """One line of prose, with the four forms the documents use."""
    def hold(found):
        kept.append(html.escape(found.group(1)))
        return KEPT % (len(kept) - 1)

    text = CODE.sub(hold, text)
    text = html.escape(text)
    text = LINK.sub(
        lambda f: '<a href="%s">%s</a>' % (html.escape(link(f.group(2))),
                                           f.group(1)),
        text)
    # A bare address goes through the same rewriting as a written link.
    # The first edition let it through untouched, and the one place in
    # the documents where the site links to itself stayed an outside
    # host — on a page whose whole claim is that there are none.
    text = BARE.sub(
        lambda f: '<a href="%s">%s</a>' % (html.escape(link(f.group(0))),
                                           f.group(0)),
        text)
    text = BOLD.sub(r"<strong>\1</strong>", text)
    text = ITALIC.sub(r"<em>\1</em>", text)
    return text


def restore(text, kept):
    for at, one in enumerate(kept):
        text = text.replace(KEPT % at, "<code>%s</code>" % one)
    return text


def headings(lines):
    """The depth of every heading, skipping fenced code.

    A shell comment inside a code block starts with `# ` too, and
    counting it made `docs/DEBUGGING.md` look like a document with two
    top-level headings: its contents came out with one entry instead of
    eight.
    """
    out = []
    inside = False
    for one in lines:
        if FENCE.match(one):
            inside = not inside
            continue
        if inside:
            continue
        found = HEADING.match(one)
        if found:
            out.append(len(found.group(1)))
    return out


def render(source, link):
    """(html, contents) for a document.

    The page shows the document's title in its first screen, so the body
    starts at `h2` — and how far the levels shift depends on the
    document. Most have one `#` and then `##` sections: there the `#` is
    the title, it is dropped, and `##` becomes `h2`. The plan has a `#`
    per milestone: there `#` becomes `h2` and nothing is dropped.

    The first edition shifted by a fixed amount and the contents came
    out empty on nine documents of eleven — they were built from `h2`,
    and `h2` was a level nobody was using.
    """
    lines = source.replace("\r\n", "\n").split("\n")
    lone = sum(1 for one in headings(lines) if one == 1) == 1
    out = []
    contents = []
    kept = []
    taken = {}
    at = 0
    end = len(lines)

    def prose(text):
        return restore(inline(text, link, kept), kept)

    while at < end:
        line = lines[at]

        found = FENCE.match(line)
        if found:
            at += 1
            block = []
            while at < end and not FENCE.match(lines[at]):
                block.append(html.escape(lines[at]))
                at += 1
            at += 1
            out.append("<pre>" + "\n".join(block) + "</pre>")
            continue

        if RULE.match(line):
            out.append('<hr class="seam">')
            at += 1
            continue

        found = HEADING.match(line)
        if found:
            deep = len(found.group(1))
            level = min(deep + (0 if lone else 1), 6)
            title = found.group(2).strip()
            # The document's own `#` is the page title and is shown in
            # the first screen; repeating it at the top of the body
            # would be the same words twice with nothing between them.
            if lone and deep == 1:
                at += 1
                continue
            name = slug(title, taken)
            out.append('<h%d id="%s">%s</h%d>'
                       % (level, name, prose(title), level))
            if level == 2:
                contents.append((name, TAG.sub("", prose(title))))
            at += 1
            continue

        if QUOTE.match(line):
            block = []
            while at < end and QUOTE.match(lines[at]):
                block.append(QUOTE.match(lines[at]).group(1))
                at += 1
            out.append("<blockquote>%s</blockquote>" % prose(" ".join(block)))
            continue

        found = ROW.match(line)
        if found and at + 1 < end and SPLIT.match(lines[at + 1]):
            head = [one.strip() for one in found.group(1).split("|")]
            at += 2
            body = []
            while at < end and ROW.match(lines[at]):
                body.append([one.strip() for one in
                             ROW.match(lines[at]).group(1).split("|")])
                at += 1
            rows = ["<table>", "<thead><tr>"]
            rows += ["<th>%s</th>" % prose(one) for one in head]
            rows.append("</tr></thead>")
            if body:
                rows.append("<tbody>")
                for cells in body:
                    rows.append("<tr>" + "".join(
                        "<td>%s</td>" % prose(one) for one in cells) + "</tr>")
                rows.append("</tbody>")
            rows.append("</table>")
            out.append("".join(rows))
            continue

        if BULLET.match(line) or NUMBER.match(line):
            ordered = NUMBER.match(line) is not None
            items = []
            while at < end:
                found = (NUMBER if ordered else BULLET).match(lines[at])
                if not found:
                    break
                items.append(found.group(1))
                at += 1
                # A wrapped item continues on the next line, indented
                # and with no marker of its own.
                while (at < end and lines[at].startswith(("  ", "\t"))
                       and lines[at].strip()
                       and not BULLET.match(lines[at])
                       and not NUMBER.match(lines[at])):
                    items[-1] += " " + lines[at].strip()
                    at += 1
            tag = "ol" if ordered else 'ul class="plain"'
            shut = "ol" if ordered else "ul"
            out.append("<%s>%s</%s>" % (
                tag, "".join("<li>%s</li>" % prose(one) for one in items),
                shut))
            continue

        # Three directives, and no HTML in the Markdown path. The plan
        # folds every task away behind `details`, and the first edition
        # wrote the tags into the text — where the rule below, which
        # strips repository furniture, dutifully ate them.
        if line.startswith("::"):
            word, _, rest = line[2:].partition(" ")
            if word == "details":
                out.append("<details>")
            elif word == "summary":
                out.append("<summary>%s</summary>" % prose(rest.strip()))
            elif word == "end":
                out.append("</details>")
            at += 1
            continue

        if line.startswith("<"):
            # Raw HTML in a document is repository furniture: badges, a
            # centred logo, a screenshot. The words inside are kept, the
            # markup is not — the site has its own header, and the
            # screenshots are deliberately gone from it.
            block = []
            while at < end and lines[at].strip():
                block.append(lines[at])
                at += 1
            said = TAG.sub(" ", " ".join(block))
            said = " ".join(said.split())
            if said:
                out.append("<p>%s</p>" % prose(said))
            continue

        if not line.strip():
            at += 1
            continue

        block = []
        while at < end and lines[at].strip() and not (
                HEADING.match(lines[at]) or RULE.match(lines[at])
                or FENCE.match(lines[at]) or BULLET.match(lines[at])
                or NUMBER.match(lines[at]) or QUOTE.match(lines[at])
                or ROW.match(lines[at]) or lines[at].startswith("<")
                or lines[at].startswith("::")):
            block.append(lines[at].strip())
            at += 1
        said = prose(" ".join(block))
        # A paragraph that is one bold run is a lead-in, not a statement
        # inside the flow: the documents use it that way, and the page
        # has a class for exactly that.
        whole = re.fullmatch(r"<strong>(.*)</strong>", said)
        out.append("<p%s>%s</p>" % (' class="lead-in"' if whole else "", said))

    return "\n".join(out), contents
