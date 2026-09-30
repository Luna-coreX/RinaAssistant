"""
Converting units, from the home screen.

A plugin that **does** something rather than showing something — the
other half of the pair with `rates`. What it demonstrates is the whole
interactive path of a tile: a field of its own on the home screen, a
press dispatched to `on_action`, and the tile redrawn from the answer.

**Why this and not a timer or a launcher.** A tile is redrawn when a
person lands on the home screen and when they press something on it —
never on its own. That suits a thing that answers a question and rules
out a thing that counts down. And a launcher would have to start
programs from `on_action`, which is exactly the way round
[ADR 0010](../../docs/adr/0010-plugin-api.md) forbids: a plugin
declares a tool and the core decides whether it may run, rather than
reaching for `subprocess` behind the permission gate.

**No permissions at all.** The arithmetic is here, nothing is read and
nothing leaves the machine. A plugin asking for nothing is a plugin a
person can enable without thinking about it, and there should be more
of those.

The last answer is kept in the plugin's own settings, so that the tile
has something to show when the program is started again — an empty
field with a hint under it is a worse greeting than the answer you got
yesterday.
"""
from plugins.api import Plugin, PluginTool
from plugins.page_spec import Card, Input, Note, Text
from plugins.convert.units import convert

from core.tools import Param

#: What the field says when it is empty. Three, and they rotate by
#: nothing — the first is the one people try.
HINT = "5 км в мили"


class ConvertPlugin(Plugin):
    """Units, one line at a time."""

    # --- the tile -------------------------------------------------------
    def home(self):
        """
        A field, and the last answer over it.

        The answer stands above the field rather than below it: after a
        press the eye is still where the answer appeared, and a line
        that turns up under the field is a line found on the second
        look.
        """
        said = self.ctx.get_setting("last", "") if self.ctx else ""
        trouble = self._trouble

        lines = []
        if trouble:
            lines.append(Note(trouble))
        elif said:
            lines.append(Text(said))
        else:
            lines.append(Note(f"Например: «{HINT}»"))

        lines.append(Input("convert", placeholder=HINT, button="="))
        return [Card(lines, title="Пересчёт")]

    #: What went wrong with the last thing typed. Not kept in the
    #: settings: a refusal belongs to the attempt, and a person coming
    #: back tomorrow should not be met by yesterday's mistake.
    _trouble = ""

    def on_action(self, action, value=None):
        """
        Something was typed and sent.

        The page is rebuilt after this call by the application, so there
        is nothing to redraw here — only something to remember.
        """
        if action != "convert":
            return
        answer, trouble = convert(str(value or ""))
        self._trouble = trouble
        if answer:
            self.ctx.set_setting("last", answer)

    # --- and the same thing out loud -------------------------------------
    def tools(self):
        return [
            PluginTool(
                name="convert_units",
                summary="Перевести величину из одних единиц в другие: "
                        "длину, массу, объём, скорость, температуру.",
                params=(
                    Param("what", "string",
                          "Что перевести, например «5 км в мили»",
                          required=True),
                ),
                run=lambda args: self._aloud(str(args.get("what", ""))),
            ),
        ]

    def on_command(self, text):
        """
        «переведи 5 км в мили» — and nothing else.

        Deliberately narrow. A plugin that answered every phrase with a
        number and a unit in it would answer questions meant for the
        calculator, for reminders and for whoever comes next.
        """
        low = text.lower().strip()
        for opener in ("переведи ", "переведите ", "конвертируй ",
                       "сколько будет ", "пересчитай "):
            if low.startswith(opener):
                self.respond(self._aloud(low[len(opener):]))
                return True
        return False

    def _aloud(self, said):
        answer, trouble = convert(said)
        return answer or trouble
