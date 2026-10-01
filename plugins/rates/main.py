"""
The dollar and the euro by the Central Bank (`4.0b-K07`).

A tile on the home screen, an answer aloud, and a block for a person's own
commands. It began as one of the examples of the plugin API and ships now,
so it answers the way a product has to: the block's answer stands inside a
sentence a person wrote — «Курс: {курс}» → «Курс: доллар 82,12 рубля, евро
94,50 рубля» — and an answer it cannot vouch for says so.

**It must not go to the network from `home`.** The tile is drawn every
time a person lands on the home screen, and a request from the drawing
path means a request per glance and a screen that waits for somebody
else's server before it appears. So the rate is fetched on a schedule of
its own and the tile answers from memory — with the date the rate is
for, because a number without a date is a number nobody can judge.

**Without a network, the last rate known is given with its date**, and
the tile says the connection is gone. Before `4.0b-K07` a question aloud
whose fetch failed answered with the old rate as though it were new; and
with nothing known at all it "succeeded" with the words «Не смогла узнать
курс», which the "find out" step would have put into a greeting. Now that
is a refusal (`ToolFailed`).

**Where the numbers come from: the Central Bank itself, and nobody
else.** It publishes them once a working day at
`cbr.ru/scripts/XML_daily.asp`. This plugin used to read a JSON mirror
at `cbr-xml-daily.ru` first, for its UTF-8 and its "previous" field —
which meant a third party saw every request, while the product page
said "a request to the central bank's website". Decided 2026-09-29: the
bank only, and one request at a time: yesterday's rate, once asked for
an arrow on the tile, is not asked for since the tile became one line.

**Permission.** `network.external` stands in the manifest, and what
leaves the machine is said on the plugin's card before it is switched on
(`sends`); a tool asking for the network without it in the manifest is
not registered by the core. Nobody is asked separately: switching the
plugin on is the consent, which is why the card has to say it plainly.
The tile's own fetch is a different matter and worth being honest about: a plugin lives in a process of its own, and
that process can open a socket whatever the manifest says. The split
isolates crashes, not capabilities — the gate is on the tools the core
registers ([ADR 0010](../../docs/adr/0010-plugin-api.md)), and a plugin
that declared nothing and went to the network anyway would be lying to
the person rather than to the machine.
"""
import re
import threading
import time
import urllib.request
from datetime import date

from plugins.api import Plugin, PluginTool, ToolFailed, vary
from plugins.page_spec import Card, Note, Row, Stat

#: Where the numbers come from.
SOURCE = "https://www.cbr.ru/scripts/XML_daily.asp"

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

#: The home screen's picture for each (`plugins/page_spec.py::ICONS`).
ICONS = {"USD": "dollar", "EUR": "euro"}

#: How each is named aloud.
NAMES = {"USD": "доллар", "EUR": "евро"}

#: Months as a date is said: «на 1 октября».
MONTHS = ("января", "февраля", "марта", "апреля", "мая", "июня", "июля",
          "августа", "сентября", "октября", "ноября", "декабря")

#: The questions the plugin takes. Whole words, and both kinds needed — a
#: rate and a currency — so «курс лечения» and «какой курс выбрать» are
#: left to whoever understands them.
CURRENCY_WORDS = ("доллар", "евро", "валют", "рубл", "$", "€")


class RatesPlugin(Plugin):
    """The dollar and the euro, in roubles."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        #: What was last fetched: {"USD": roubles}, the date the
        #: bank set it for, and when it was asked.
        self._rates = {}
        self._dated = None
        self._asked_at = 0.0
        self._asking = False
        self._trouble = ""

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
        Two figures on the home screen: «$ 83,56 ₽» and «€ 94,88 ₽».

        Asked for by a person (2026-10-02): a glance, as the weather has —
        the sign, the rate large, the currency's name small. Before the
        first answer it says it is looking rather than being absent, and a
        rate it could not refresh says the date it is for.
        """
        self._refresh_if_stale()

        if not self._rates:
            return [Note(self._trouble or "Смотрю курс…")]

        figures = []
        for code in SHOWN:
            if code not in self._rates:
                continue
            caption = NAMES[code]
            if (not figures and self._trouble and not self._fresh()
                    and self._dated is not None):
                caption += f" · на {spoken_date(self._dated)}"
            figures.append(Stat(f"{money(self._rates[code])} ₽", caption,
                                ICONS[code]))
        return [Card([Row(figures)])]

    # --- aloud, and as a block -------------------------------------------
    def tools(self):
        return [
            PluginTool(
                name="rates",
                summary="Курс доллара и евро по Центробанку.",
                # Reads and answers (`4.0-H10`): said when a scenario runs
                # it, and kept by the "find out" step.
                reads=True,
                title="Курс валют",
                run=lambda args: self._said(),
                permissions=("network.external",),
            ),
        ]

    def on_command(self, text):
        low = text.lower()
        if "курс" not in low:
            return False
        if not any(word in low for word in CURRENCY_WORDS):
            return False
        try:
            self.respond(self._said()["say"])
        except ToolFailed as refusal:
            self.respond(str(refusal))
        return True

    def _said(self):
        """
        The rate, fetched now if what is kept is old, in both forms: the
        sentence said aloud and the value the "find out" step keeps.

        Out loud the rate is asked **now** and waited for — the opposite of
        the tile's rule, because a person who asked is standing there. When
        the asking fails, the last rate known is given with the date it is
        for; with nothing known, the answer is a refusal in words.
        """
        if not self._fresh():
            self._fetch()
        if not self._rates:
            raise ToolFailed(self._trouble or "Курс узнать не вышло.")
        usd, eur = (self._rates.get(code) for code in SHOWN)
        if usd is None or eur is None:
            value = ", ".join(f"{NAMES[code]} {money(self._rates[code])} рубля"
                              for code in SHOWN if code in self._rates)
            say = f"По Центробанку {value}."
        else:
            usd, eur = money(usd), money(eur)
            value = vary(f"доллар {usd} рубля, евро {eur} рубля",
                         f"доллар по {usd}, евро по {eur}")
            say = vary(f"По Центробанку доллар {usd} рубля, евро {eur} рубля.",
                       f"Доллар сегодня {usd}, евро — {eur} рубля.",
                       f"Центробанк даёт {usd} за доллар и {eur} за евро.")
        if not self._fresh() and self._dated is not None:
            day = spoken_date(self._dated)
            value += f" (курс на {day})"
            say += " " + vary(f"Это курс на {day} — свежий узнать не вышло.",
                              f"Правда, курс на {day}: обновить не получилось.")
        return {"say": say, "value": value}

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
            # One request. Yesterday's rate was asked for as well, for an
            # arrow on the tile; the tile is one plain line now, and a
            # request for something nobody is shown is a request somebody
            # else's server need not have seen.
            today, dated = self._from_bank()
            if today:
                self._rates = dict(today)
                self._dated = dated
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

    def _from_bank(self, day=None):
        """
        The Central Bank's XML: {code: roubles per unit}, and its date.

        Parsed with a regular expression rather than an XML library, and
        that is a deliberate smallness: three fields of a document whose
        shape has not changed since the two thousands. Windows-1251 and a
        comma for a decimal point. `day` asks for the rates set for that
        date; without it, for today.
        """
        url = SOURCE
        if day is not None:
            url += "?date_req=" + day.strftime("%d/%m/%Y")
        request = urllib.request.Request(
            url, headers={"User-Agent": "RinaAssistant"})
        with urllib.request.urlopen(request, timeout=PATIENCE) as answer:
            page = answer.read().decode("windows-1251", "replace")
        return parse_bank(page)


def spoken_date(day):
    """«1 октября» — the way the date of a rate is said."""
    return f"{day.day} {MONTHS[day.month - 1]}"


def parse_bank(page):
    """
    The bank's document: ({code: roubles per unit}, the date it is for).

    Separate from the fetching so that it can be asked about without a
    network. The date is `<ValCurs Date="30.09.2026">`; a document without
    one gives no date, and the day before it is then not asked for.
    """
    dated = None
    found = re.search(r'<ValCurs[^>]*\bDate="(\d{2})\.(\d{2})\.(\d{4})"', page)
    if found:
        try:
            dated = date(int(found.group(3)), int(found.group(2)),
                         int(found.group(1)))
        except ValueError:
            dated = None
    out = {}
    for block in re.findall(r"<Valute\b.*?</Valute>", page, re.S):
        code = re.search(r"<CharCode>(\w+)</CharCode>", block)
        value = re.search(r"<Value>([\d,\.]+)</Value>", block)
        nominal = re.search(r"<Nominal>(\d+)</Nominal>", block)
        if not code or not value or code.group(1) not in SHOWN:
            continue
        per = float(nominal.group(1)) if nominal else 1.0
        out[code.group(1)] = float(value.group(1).replace(",", ".")) / (per or 1.0)
    return out, dated


def money(value):
    """A rate the way a rate is written: two places, a comma."""
    return f"{value:.2f}".replace(".", ",")
