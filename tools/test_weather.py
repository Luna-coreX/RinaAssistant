# -*- coding: utf-8 -*-
"""
4.0b-K06: the weather plugin, without a network.

The source is substituted: what Open-Meteo answers is written here in the
shape it was seen to answer on 2026-10-01, and the plugin is driven the way
the core drives it. Checked:

- the answer is a fragment that stands inside a sentence a person wrote,
  with Russian numbers agreeing — «1 градус», «2 градуса», «5 градусов»;
- "until the evening" is counted on the city's own clock, and the
  thresholds keep «обещают» for what the forecast actually promises;
- without a network the last answer is given **with the time it is for**,
  and with nothing known the tool refuses in words rather than putting an
  error into a greeting;
- the plugin takes only whole questions about the weather, so «поищи
  погоду в Москве» still reaches the search.

To run:
    python tools/test_weather.py
"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

from console import use_utf8

use_utf8()

from plugins.api import PluginManifest, ToolFailed
from plugins.weather import main as weather_main
from plugins.weather import source, words

fails = 0


def check(label, cond, detail=""):
    global fails
    if not cond:
        fails += 1
    print(("OK   " if cond else "FAIL "), label, detail)


def day(now, chances, codes=None, temperature=7.0, code=3):
    """A forecast in Open-Meteo's shape: now, and the day hour by hour."""
    hours = [f"2026-10-01T{h:02d}:00" for h in range(24)]
    return {"current": {"time": f"2026-10-01T{now}", "temperature_2m": temperature,
                        "weather_code": code},
            "hourly": {"time": hours,
                       "precipitation_probability": chances,
                       "weather_code": codes or [3] * 24}}


# ---------------------------------------------------------------------------
print("=== числа по-русски ===")
for value, said in ((1, "1 градус"), (2, "2 градуса"), (5, "5 градусов"),
                    (11, "11 градусов"), (12, "12 градусов"),
                    (21, "21 градус"), (22, "22 градуса"), (0.4, "ноль градусов"),
                    (-3.2, "минус 3 градуса"), (-1, "минус 1 градус")):
    check(f"{value} → «{said}»", words.degrees(value) == said,
          f"| {words.degrees(value)}")
check("минуты назад", words.ago(12 * 60) == "12 минут назад"
      and words.ago(61 * 60) == "1 час назад" and words.ago(30) == "только что")

# ---------------------------------------------------------------------------
print()
print("=== до вечера — по часам города ===")
dry = day("06:30", [5] * 24)
check("сухо — «дождя до вечера не обещают»",
      words.outlook(dry) == "дождя до вечера не обещают", f"| {words.outlook(dry)}")
check("и фраза встаёт после «На улице»",
      words.now_said(dry) == "7 градусов, пасмурно, дождя до вечера не обещают",
      f"| {words.now_said(dry)}")

wet = day("09:10", [5] * 15 + [70] * 9)
check("дождь к трём — «к 15:00 обещают дождь»",
      words.outlook(wet) == "к 15:00 обещают дождь", f"| {words.outlook(wet)}")

maybe = day("09:10", [5] * 13 + [40] * 11)
check("сорок процентов — «возможен», а не «обещают»",
      words.outlook(maybe) == "к 13:00 возможен дождь", f"| {words.outlook(maybe)}")

past = day("19:00", [90] * 12 + [5] * 12)
check("утренний дождь вечером не обещают",
      words.outlook(past) == "дождя до ночи не обещают", f"| {words.outlook(past)}")

snow = day("08:00", [5] * 10 + [80] * 14, codes=[3] * 10 + [73] * 14,
           temperature=-2)
check("снег называется снегом",
      words.outlook(snow) == "к 10:00 обещают снег", f"| {words.outlook(snow)}")
check("и мороз — с «минус»",
      words.now_said(snow).startswith("минус 2 градуса"), f"| {words.now_said(snow)}")

# ---------------------------------------------------------------------------
print()
print("=== какие фразы плагин берёт себе ===")
for phrase in ("какая погода", "Какая погода?", "что на улице",
               "будет ли сегодня дождь", "what's the weather"):
    check(f"«{phrase}» — его", words.asks(phrase))
for phrase in ("поищи погоду в москве", "погода в токио на завтра",
               "расскажи про погоду на марсе"):
    check(f"«{phrase}» — не его", not words.asks(phrase))

# ---------------------------------------------------------------------------
print()
print("=== плагин целиком, с подменённым источником ===")


class Ctx:
    """What the core gives a plugin: its settings, its log, its voice."""

    def __init__(self):
        self.kept, self.said, self.logged = {}, [], []
        self.manifest = PluginManifest.from_dict(
            {"id": "weather", "name": "Погода", "api_version": 4},
            path=os.path.join(ROOT, "plugins", "weather"))

    def get_setting(self, key, default=None):
        return self.kept.get(key, default)

    def set_setting(self, key, value):
        self.kept[key] = value

    def log(self, message):
        self.logged.append(message)

    def respond(self, text):
        self.said.append(text)


# ---------------------------------------------------------------------------
print()
print("=== что уходит наружу (T-26) ===")
# The real `source` functions, with the network itself substituted: what
# would be sent is captured at the last step before a socket.
sent = []


class Answer:
    def __init__(self, body):
        self.body = body

    def read(self):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def capture(request, timeout=None):
    sent.append(request)
    body = (b'{"results": [{"name": "\xd0\x9a\xd0\xb0\xd0\xb7\xd0\xb0\xd0\xbd\xd1\x8c",'
            b' "latitude": 55.79, "longitude": 49.12, "timezone": "Europe/Moscow"}]}'
            if "geocoding" in request.full_url else b"{}")
    return Answer(body)


import urllib.parse
import urllib.request

real_urlopen = urllib.request.urlopen
urllib.request.urlopen = capture
try:
    place = source.find_city("Казань")
    source.forecast(place)
finally:
    urllib.request.urlopen = real_urlopen


def keys(request):
    return set(urllib.parse.parse_qs(
        urllib.parse.urlsplit(request.full_url).query))


check("поиск города получает только название",
      keys(sent[0]) == {"name", "count", "language", "format"},
      f"| {sorted(keys(sent[0]))}")
check("прогноз — только координаты и что спросить",
      keys(sent[1]) == {"latitude", "longitude", "current", "hourly",
                        "timezone", "forecast_days"},
      f"| {sorted(keys(sent[1]))}")
check("ни ключа, ни имени, ни идентификатора в заголовках",
      all(set(r.headers) == {"User-agent"} for r in sent)
      and all("Rina" in r.headers["User-agent"] for r in sent),
      f"| {[r.headers for r in sent]}")
check("и всё уходит только в Open-Meteo",
      all(urllib.parse.urlsplit(r.full_url).hostname.endswith("open-meteo.com")
          for r in sent))

asked = []
online = {"up": True, "data": dry}


def find_city(name):
    asked.append(("city", name))
    if not online["up"]:
        raise OSError("нет сети")
    if name.lower() == "нигдеград":
        return None
    return {"name": "Казань", "country": "Россия", "latitude": 55.79,
            "longitude": 49.12, "timezone": "Europe/Moscow"}


def forecast(place):
    asked.append(("forecast", place["name"]))
    if not online["up"]:
        raise OSError("нет сети")
    return online["data"]


source.find_city, source.forecast = find_city, forecast

ctx = Ctx()
plugin = weather_main.WeatherPlugin(ctx)
tool = plugin.tools()[0]
check("инструмент объявлен читающим блоком «Погода»",
      tool.reads and tool.title == "Погода")

try:
    tool.run({})
    check("без города — отказ словами", False)
except ToolFailed as refusal:
    check("без города — отказ словами", "город" in str(refusal).lower(),
          f"| {refusal}")
tile = plugin.home()
check("плитка без города просит его ввести",
      any(e.kind == "input" for card in tile for e in card.children),
      f"| {[e.kind for card in tile for e in card.children]}")

plugin.on_action("city", "нигдеград")
check("несуществующий город назван", "нигдеград" in plugin._trouble,
      f"| {plugin._trouble}")
check("и не сохранён", ctx.get_setting("place") is None)

plugin.on_action("city", "Казань")
check("город сохранён с координатами",
      (ctx.get_setting("place") or {}).get("latitude") == 55.79)
deadline = time.time() + 5
while plugin._data is None and time.time() < deadline:
    time.sleep(0.05)
said = tool.run({})
check("ответ блока — фрагмент для фразы",
      said == "7 градусов, пасмурно, дождя до вечера не обещают", f"| {said}")

before = len(asked)
tool.run({})
check("свежие данные не запрашиваются снова",
      len(asked) == before, f"| {asked[before:]}")

home = plugin.home()
check("плитка подписана источником (CC BY 4.0)",
      any("Open-Meteo" in str(e.text) for card in home for e in card.children))

# The network goes, and the data gets old.
online["up"] = False
plugin._asked_at -= weather_main.FRESH_FOR + 60
said = tool.run({})
check("без сети — последнее известное, с временем, на которое оно",
      said.startswith("7 градусов") and "по данным на 6:30" in said, f"| {said}")
caption = [e.text for card in plugin.home() for e in card.children][-1]
check("и плитка говорит, что связи нет", "нет связи" in str(caption),
      f"| {caption}")

empty = weather_main.WeatherPlugin(Ctx())
empty.ctx.set_setting("place", ctx.get_setting("place"))
try:
    empty.tools()[0].run({})
    check("без сети и без данных — отказ словами", False)
except ToolFailed as refusal:
    check("без сети и без данных — отказ словами", "нет связи" in str(refusal),
          f"| {refusal}")

online["up"] = True
heard = Ctx()
aloud = weather_main.WeatherPlugin(heard)
aloud.ctx.set_setting("place", ctx.get_setting("place"))
check("вопрос вслух взят", aloud.on_command("какая погода"))
check("и ответ назвал город", heard.said[:1] and heard.said[0].startswith("Казань: 7 градусов"),
      f"| {heard.said}")
check("чужая фраза не взята", not aloud.on_command("поищи погоду в москве"))

print()
print("ИТОГО ошибок:", fails)
sys.exit(1 if fails else 0)
