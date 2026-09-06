"""
The declarative description of a plugin's page (the version 2 schema).

A plugin used to return a ready-made QWidget. That is convenient exactly as
long as the interface is written in Qt: such a plugin cannot be shown in
another shell and cannot be drawn outside the Python process.

So a plugin describes the page as a list of elements, and the shell draws
them:

    from plugins.api import Plugin
    from plugins.page_spec import Card, Title, Note, Items, Button, Row

    class NotesPlugin(Plugin):
        def page(self):
            notes = self.ctx.get_setting("items", []) or []
            return [
                Card([
                    Title("Мои заметки"),
                    Note(f"Всего: {len(notes)}"),
                    Items(notes) if notes else Note("Пока пусто"),
                ], title="Заметки"),
                Row([
                    Button("Очистить", action="clear", variant="danger"),
                    Button("Обновить", action="refresh"),
                ]),
            ]

        def on_action(self, action, value=None):
            if action == "clear":
                self.ctx.set_setting("items", [])

The elements are ordinary data with no dependency on Qt, so any shell will
draw such a page, including one not written in Python.

**The schema is semantic, not visual.** A plugin says "warning", not "an
orange border"; "a card", not "round the corners by eight pixels". There is
not one field about appearance here and there never will be: the colour, the
margin and the font are known by whoever draws. That is exactly why version
1 survived the redesign almost whole.

The full description is
[PAGE-SCHEMA-v2](../docs/plugins/PAGE-SCHEMA-v2.md).
"""

from dataclasses import dataclass, field
from typing import List, Optional

#: The schema's version. Grows on an incompatible change to the dictionary;
#: adding an element does not count as incompatible — the renderer is
#: obliged to show an unfamiliar kind rather than skip it.
SCHEMA_VERSION = 2

#: How far down the nesting the renderer is allowed to go.
#:
#: The limit is not about beauty. The description comes from another
#: process, and "as many nested cards as you like" is a way to keep the
#: shell busy drawing instead of answering a person.
MAX_DEPTH = 4

#: The kinds that have nested content.
CONTAINERS = ("card", "group", "row")

#: Every kind in the dictionary — to check against the renderer (`4.0-H02`).
KINDS = ("title", "text", "note", "items", "button", "input", "table",
         "progress", "badge", "divider") + CONTAINERS


@dataclass
class Element:
    kind: str
    text: str = ""
    items: Optional[List[str]] = None
    action: str = ""
    variant: str = "normal"      # for buttons: normal | danger
    value: object = None
    children: List["Element"] = field(default_factory=list)

    def to_dict(self):
        """
        Serialisation: the page goes to the shell as dicts.

        Empty fields are not written — a page's description travels over the
        wire on every press, and half of it would otherwise be empty
        strings.
        """
        data = {"kind": self.kind}
        if self.text:
            data["text"] = self.text
        if self.items:
            data["items"] = list(self.items)
        if self.action:
            data["action"] = self.action
        if self.variant != "normal":
            data["variant"] = self.variant
        if self.value is not None:
            data["value"] = self.value
        if self.children:
            data["children"] = [c.to_dict() for c in self.children
                                if isinstance(c, Element)]
        return data


# ---------------------------------------------------------------------------
# The leaves
# ---------------------------------------------------------------------------
def Title(text):
    """A large section heading."""
    return Element(kind="title", text=str(text))


def Text(text):
    """Ordinary text."""
    return Element(kind="text", text=str(text))


def Note(text):
    """A small explanatory caption."""
    return Element(kind="note", text=str(text))


def Items(items):
    """A list of lines (notes, tasks, results)."""
    return Element(kind="items", items=[str(i) for i in (items or [])])


def Button(label, action, variant="normal"):
    """A button. On a press the application calls plugin.on_action(action)."""
    return Element(kind="button", text=str(label), action=str(action),
                   variant=variant)


def Divider():
    """A dividing line."""
    return Element(kind="divider")


def Input(action, placeholder="", value="", button=""):
    """
    An input field. On Enter (or the button beside it) the application calls
    plugin.on_action(action, the_typed_text).
    """
    return Element(kind="input", action=str(action), text=str(placeholder),
                   value=str(value), variant=str(button or ""))


def Table(rows, headers=None):
    """
    A plain table: a list of rows, each a list of cells.
    The headings are optional.
    """
    return Element(kind="table",
                   items=[[str(c) for c in row] for row in (rows or [])],
                   value=[str(h) for h in headers] if headers else None)


def Progress(value, text=""):
    """A progress bar: value from 0.0 to 1.0."""
    try:
        ratio = max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        ratio = 0.0
    return Element(kind="progress", value=ratio, text=str(text))


def Badge(text, variant="normal"):
    """A small state label: normal | good | warn | danger."""
    return Element(kind="badge", text=str(text), variant=variant)


# ---------------------------------------------------------------------------
# The containers (the version 2 schema, `4.0-H01`)
# ---------------------------------------------------------------------------
def _kids(children):
    """Elements only: something foreign among the children means a silent empty card."""
    return [c for c in (children or []) if isinstance(c, Element)]


def Card(children, title=""):
    """
    "This is one whole thing."

    A card answers the question of what counts as one thing: one note, one
    instrument, one result. Not "draw a border round it" — a border is the
    shell's decision, and in another design a card may turn out to have no
    border at all.
    """
    return Element(kind="card", text=str(title), children=_kids(children))


def Group(children, title=""):
    """
    "This is about one thing."

    A section of a page: a heading and what is under it. It differs from a
    card in grouping **topics** rather than things — just as the sections of
    the settings screen differ from the cards in the command list.
    """
    return Element(kind="group", text=str(title), children=_kids(children))


def Row(children):
    """
    "These are next to each other."

    A request, not an order: in a narrow window the renderer is entitled to
    put the contents into a column. "Side by side" is not expressible at
    four hundred points of width, and squeezing text to two letters is worse
    than breaking the request.
    """
    return Element(kind="row", children=_kids(children))


def page_to_dict(elements):
    """The whole page as a list of dicts (to pass outwards)."""
    return [e.to_dict() for e in (elements or []) if isinstance(e, Element)]
