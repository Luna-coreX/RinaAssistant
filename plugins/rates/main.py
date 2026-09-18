"""
The rate of the dollar and the euro, as a tile on the home screen.

A plugin that only **shows**. It is the simpler of the two examples and
exists to answer one question: what does a plugin have to do to put
something on the home screen, and what must it not do there.

**It must not go to the network from `home`.** The tile is drawn every
time a person lands on the home screen, and a request from the drawing
path means a request per glance and a screen that waits for somebody
else's server before it appears. So the rate is fetched on a schedule of
its own and the tile answers from memory — with a caption saying how old
the answer is, because a number without a date is a number nobody can
judge.

**Where the numbers come from.** The Central Bank of Russia publishes
them once a working day. The official endpoint is
`cbr.ru/scripts/XML_daily.asp`; this plugin reads the JSON mirror at
`cbr-xml-daily.ru`, which serves the same data in UTF-8 and carries the
previous day's value as well — and yesterday's value is what turns a
number into a direction. The official XML is the fallback: a mirror is
somebody's goodwill, and a plugin that dies with it would be a plugin
that trusted the wrong thing.

**Permission.** `network.external` stands in the manifest, and the
person grants it before the first run; without it the core refuses to
register the `rates` tool, so Rina cannot be asked for the rate out
loud. The tile's own fetch is a different matter and worth being
honest about: a plugin lives in a process of its own, and that process
can open a socket whatever the manifest says. The split isolates
crashes, not capabilities — the gate is on the tools the core
registers ([ADR 0010](../../docs/adr/0010-plugin-api.md)), and a
plugin that declared nothing and went to the network anyway would be
lying to the person rather than to the machine.
"""
import json
import re
import threading
import time
import urllib.request

from plugins.api import Plugin, PluginTool
from plugins.page_spec import Card, Note, Row, Text

#: Where the numbers come from, best first.
MIRROR = "https://www.cbr-xml-daily.ru/daily_json.js"
OFFICIAL = "https://www.cbr.ru/scripts/XML_daily.asp"

#: How long to wait for somebody else's server. Short on purpose: this
#: runs on a thread of its own, but a thread that waits a minute is a
#: thread that is still waiting when the person has moved on.
PATIENCE = 6.0

#: How long a rate is worth showing without asking again. The Central
#: Bank sets it once a working day, so a quarter of an hour is already
#: far more often than the thing changes; it exists to catch the change
#: of day rather than to keep up with a market.
FRESH_FOR = 900.0

#: What is shown. Two, and deliberately two: a tile with a dozen
#: currencies on it is a table, and there is a page for a table.
SHOWN = ("USD", "EUR")

SIGNS = {"USD": "$", "EUR": "€"}


class RatesPlugin(Plugin):
    """The dollar and the euro, in roubles."""

    #: What was last fetched: {"USD": (value, previous)}, and when.
    _rates: dict = {}
    _asked_at: float = 0.0
    _asking: bool = False
    _trouble: str = ""

    def on_enable(self):
        """
        Ask straight away, rather than on the first glance.

        The tile answers from memory, and before the first fetch the
        memory is empty — so the first time a person lands on the home
        screen they read «Смотрю курс…» and have to come back. The
        plugin knows it will be asked; it may as well ask first.
        """
        self._refresh_if_stale()

    # --- the tile -------------------------------------------------------
    def home(self):
        """
        Two lines and a caption, and never a request.

        Before the first answer the tile says it is looking rather than
        being absent: a plugin that appears only once it has succeeded
        looks broken until then, and "looking" is a state worth showing.
        """
        self._refresh_if_stale()

        if not self._rates:
            return [Card([Note(self._trouble or "Смотрю курс…")],
                         title="Курс")]

        lines = []
        for code in SHOWN:
            got = self._rates.get(code)
            if got is None:
                continue
            value, previous = got
            lines.append(Row([Text(f"{SIGNS.get(code, code)} {money(value)} ₽"),
                              Note(step(value, previous))]))

        lines.append(Note(self._said_when()))
        return [Card(lines, title="Курс")]

    # --- and the same thing out loud -------------------------------------
    def tools(self):
        return [
            PluginTool(
                name="rates",
                summary="Сказать курс доллара и евро по Центробанку.",
                run=lambda args: self._aloud(),
                permissions=("network.external",),
            ),
        ]

    def on_command(self, text):
        low = text.lower()
        if "курс" not in low:
            return False
        if not any(word in low
                   for word in ("доллар", "евро", "валют", "рубл", "$", "€")):
            return False
        self.respond(self._aloud())
        return True

    def _aloud(self):
        """
        Out loud the rate is fetched **now**, and waited for.

        The opposite rule to the tile's, and for the opposite reason: a
        person who asked is standing there waiting for an answer, and
        yesterday's number given without being asked for yesterday's is
        a wrong answer. A tile is a glance; a question is a question.
        """
        if not self._fresh():
            self._fetch()
        if not self._rates:
            return self._trouble or "Не смогла узнать курс."
        said = ", ".join(
            f"{name}: {money(self._rates[code][0])} рубля"
            for code, name in (("USD", "доллар"), ("EUR", "евро"))
            if code in self._rates)
        return f"По Центробанку {said}."

    # --- the fetching -----------------------------------------------------
    def _fresh(self):
        return bool(self._rates) and time.time() - self._asked_at < FRESH_FOR

    def _refresh_if_stale(self):
        """Ask again, on a thread of its own, and never twice at once."""
        if self._fresh() or self._asking:
            return
        self._asking = True
        threading.Thread(target=self._fetch, daemon=True,
                         name="rates").start()

    def _fetch(self):
        try:
            got = self._from_mirror()
            if not got:
                got = self._from_official()
            if got:
                self._rates = got
                self._asked_at = time.time()
                self._trouble = ""
            else:
                self._trouble = "Курс не пришёл."
        except Exception as exc:                         # noqa: BLE001
            # Somebody else's server, somebody else's network. The tile
            # says so and goes on standing there; a plugin that throws
            # here would be marked broken and taken off the screen for
            # the rest of the session.
            self.log(f"курс не пришёл: {exc.__class__.__name__}: {exc}")
            self._trouble = "Курс не пришёл: нет связи."
        finally:
            self._asking = False

    def _from_mirror(self):
        with urllib.request.urlopen(MIRROR, timeout=PATIENCE) as answer:
            data = json.loads(answer.read().decode("utf-8"))
        out = {}
        for code in SHOWN:
            one = (data.get("Valute") or {}).get(code)
            if not one:
                continue
            nominal = float(one.get("Nominal") or 1) or 1
            out[code] = (float(one["Value"]) / nominal,
                         float(one.get("Previous") or 0) / nominal)
        return out

    def _from_official(self):
        """
        The Central Bank's own XML, when the mirror is silent.

        Parsed with a regular expression rather than an XML library, and
        that is a deliberate smallness: three fields of a document whose
        shape has not changed since the two thousands. Windows-1251, a
        comma for a decimal point, and no previous day — hence the
        mirror first.
        """
        request = urllib.request.Request(
            OFFICIAL, headers={"User-Agent": "RinaAssistant"})
        with urllib.request.urlopen(request, timeout=PATIENCE) as answer:
            page = answer.read().decode("windows-1251", "replace")

        out = {}
        for block in re.findall(r"<Valute\b.*?</Valute>", page, re.S):
            code = re.search(r"<CharCode>(\w+)</CharCode>", block)
            value = re.search(r"<Value>([\d,\.]+)</Value>", block)
            nominal = re.search(r"<Nominal>(\d+)</Nominal>", block)
            if not code or not value or code.group(1) not in SHOWN:
                continue
            per = float(nominal.group(1)) if nominal else 1.0
            out[code.group(1)] = (
                float(value.group(1).replace(",", ".")) / (per or 1.0), 0.0)
        return out

    def _said_when(self):
        if not self._asked_at:
            return ""
        ago = int(time.time() - self._asked_at)
        if ago < 90:
            return "Центробанк, только что"
        return f"Центробанк, {ago // 60} мин назад"


def money(value):
    """A rate the way a rate is written: two places, a comma."""
    return f"{value:.2f}".replace(".", ",")


def step(value, previous):
    """Which way it went since the day before — or nothing, if unknown."""
    if not previous:
        return ""
    difference = value - previous
    if abs(difference) < 0.005:
        return "без изменений"
    mark = "▲" if difference > 0 else "▼"
    return f"{mark} {money(abs(difference))}"
