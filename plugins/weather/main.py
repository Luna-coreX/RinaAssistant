"""
The weather: now and until the evening (`4.0b-K06`).

A tile on the home screen, an answer aloud, and a block for a person's own
commands. The block is the reason the answer is worded the way it is: it
goes into a sentence somebody wrote — «На улице {погода}» — so it is a
fragment that fits after «На улице», not a report with its own heading.

**The tile never goes to the network**, for the reason the rate tile does
not: it is drawn on every glance. The weather is fetched on a thread of its
own at most every half hour, and the tile answers from memory with the time
the data is for. A question aloud waits for fresh data instead — a person
who asked is standing there — and when the network is gone it says how old
its answer is rather than passing an old one off as new.

The city is typed on the plugin's page or tile. The core does not build a
plugin's settings panel in 4.0 (`4.0-H08`), and a city is one field; an
input next to the weather is where a person looks for it anyway.
"""
import threading
import time

from plugins.api import Plugin, PluginTool, ToolFailed
from plugins.page_spec import Card, Input, Note, Text
from plugins.weather import source, words

#: How long the weather is worth showing without asking again.
FRESH_FOR = 1800.0

#: Named on every screen that shows the data: CC BY 4.0 asks for it.
CREDIT = "Open-Meteo"


class WeatherPlugin(Plugin):
    """The weather for one city."""

    page_title = "Погода"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._data = None
        self._asked_at = 0.0
        self._asking = False
        self._trouble = ""
        # One fetch at a time: the tile's thread and a question aloud can
        # arrive together, and two answers racing to be "the last one" is
        # how a tile ends up showing the older of the two.
        self._lock = threading.Lock()

    def on_enable(self):
        """Ask straight away, so the first glance is not «Смотрю погоду…»."""
        self._refresh_if_stale()

    # --- the place ---------------------------------------------------------
    def _place(self):
        place = self.ctx.get_setting("place", None)
        return place if isinstance(place, dict) and "latitude" in place \
            else None

    def _set_city(self, typed):
        """Find the city by its name and keep it. Said, if it cannot be found."""
        typed = " ".join(str(typed or "").split())
        if not typed:
            return
        try:
            found = source.find_city(typed)
        except Exception as exc:                         # noqa: BLE001
            self.log(f"город не нашёлся: {exc.__class__.__name__}: {exc}")
            self._trouble = "Не удалось найти город: нет связи."
            return
        if found is None:
            self._trouble = f"Не нашла город «{typed}»."
            return
        self.ctx.set_setting("place", found)
        with self._lock:
            self._data, self._asked_at, self._trouble = None, 0.0, ""
        self._refresh_if_stale()

    # --- the tile and the page -----------------------------------------------
    def home(self):
        place = self._place()
        if place is None:
            return [Card([Note(self._trouble or
                               "Укажите город — и здесь будет погода."),
                          Input("city", placeholder="Город", button="OK")],
                         title="Погода")]
        self._refresh_if_stale()
        title = f"Погода · {place['name']}"
        if self._data is None:
            return [Card([Note(self._trouble or "Смотрю погоду…")],
                         title=title)]
        return [Card(self._shown(), title=title)]

    def page(self):
        place = self._place()
        lines = []
        if place is not None and self._data is not None:
            lines.extend(self._shown())
        elif place is not None:
            lines.append(Note(self._trouble or "Смотрю погоду…"))
        elif self._trouble:
            lines.append(Note(self._trouble))
        lines.append(Input("city",
                           placeholder="Город, например Казань",
                           value=place["name"] if place else "",
                           button="Сохранить"))
        lines.append(Note("Название города и его координаты уходят в "
                          "Open-Meteo, больше ничего. Данные: Open-Meteo.com, "
                          "лицензия CC BY 4.0."))
        title = f"Погода · {place['name']}" if place else "Погода"
        return [Card(lines, title=title)]

    def on_action(self, action, value=None):
        if action == "city":
            self._set_city(value)

    def _shown(self):
        current = self._data.get("current") or {}
        sky = words.SKY.get(current.get("weather_code"), "")
        temperature = current.get("temperature_2m")
        head = (f"{round(temperature):+d}°".replace("+0", "0")
                if temperature is not None else "")
        return [Text(" ".join(part for part in (head, sky) if part)),
                Note(words.outlook(self._data)),
                Note(self._caption())]

    def _caption(self):
        if self._fresh() or not self._trouble:
            return f"{CREDIT}, {words.ago(time.time() - self._asked_at)}"
        return f"{CREDIT}, данные на {words.as_of(self._data)} — нет связи"

    # --- aloud, and as a block -------------------------------------------------
    def tools(self):
        return [
            PluginTool(
                name="now",
                summary="Погода сейчас и до вечера: температура, небо и "
                        "будет ли дождь.",
                # Reads and answers (`4.0-H10`): said when a command runs
                # it, and what the "find out" step keeps under a name.
                reads=True,
                title="Погода",
                run=lambda args: self._said(),
                permissions=("network.external",),
            ),
        ]

    def on_command(self, text):
        if not words.asks(text):
            return False
        place = self._place()
        try:
            said = self._said()
        except ToolFailed as refusal:
            self.respond(str(refusal))
            return True
        self.respond(f"{place['name']}: {said}.")
        return True

    def _said(self):
        """
        The weather, fetched now if what is kept is old.

        Without a network the answer is still the last one known, with the
        time it is for: «…, по данным на 6:30». Without anything known, a
        refusal in words — the "find out" step then leaves the value
        unfilled rather than putting an error message into a greeting.
        """
        if self._place() is None:
            raise ToolFailed("Город для погоды не задан — укажите его на "
                             "вкладке «Погода».")
        if not self._fresh():
            self._fetch()
        if self._data is None:
            raise ToolFailed(self._trouble or "Погоду узнать не вышло.")
        said = words.now_said(self._data)
        if not self._fresh():
            said += f" (по данным на {words.as_of(self._data)})"
        return said

    # --- the fetching ---------------------------------------------------------
    def _fresh(self):
        return self._data is not None \
            and time.time() - self._asked_at < FRESH_FOR

    def _refresh_if_stale(self):
        """Ask again, on a thread of its own, and never twice at once."""
        if self._place() is None or self._fresh() or self._asking:
            return
        self._asking = True
        threading.Thread(target=self._fetch, daemon=True,
                         name="weather").start()

    def _fetch(self):
        place = self._place()
        if place is None:
            self._asking = False
            return
        try:
            data = source.forecast(place)
            with self._lock:
                self._data, self._asked_at, self._trouble = \
                    data, time.time(), ""
        except Exception as exc:                         # noqa: BLE001
            # Somebody else's server, somebody else's network. The tile
            # keeps what it had and says how old it is; a plugin that threw
            # here would be marked broken for the rest of the session.
            self.log(f"погода не пришла: {exc.__class__.__name__}: {exc}")
            self._trouble = "Погода не пришла: нет связи."
        finally:
            self._asking = False
