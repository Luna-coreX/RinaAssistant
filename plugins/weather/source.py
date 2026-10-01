"""
Where the weather comes from: Open-Meteo (`4.0b-K06`).

Kept in a module of its own because the source may have to change. The
free Open-Meteo API is for non-commercial use: by its terms, "private or
non-profit websites or apps that do not have subscriptions or
advertising" (open-meteo.com/en/terms, read 2026-10-01). Rina is free and
open, with neither, so it qualifies today. If paid features ever appear,
Rina becomes a commercial product and this module moves to a paid
Open-Meteo plan or to MET Norway — and nothing else in the plugin has to
know.

The data is under CC BY 4.0, which asks for the source to be named; the
tile and the page say «Open-Meteo».

What leaves the machine: the city name as the person typed it (to find
it) and the city's coordinates (to ask about it). Nothing else — no
identifier, no key. The free API has none, which is also why its limits
(10 000 calls a day, 5 000 an hour, 600 a minute, 300 000 a month) can
only be counted per address; the plugin asks every half hour at most.
"""
import json
import urllib.parse
import urllib.request

GEOCODER = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST = "https://api.open-meteo.com/v1/forecast"

#: How long to wait for somebody else's server. A tool call has ten
#: seconds before the core gives up on the plugin, and a person asking
#: aloud is waiting for less than that.
PATIENCE = 6.0

#: Who is asking. Not a secret and not an identifier of the person: the
#: program's name, so whoever runs the service can tell its traffic apart.
AGENT = "RinaAssistant (+https://www.rina-assistant.com)"


def _get(url, params):
    request = urllib.request.Request(
        url + "?" + urllib.parse.urlencode(params),
        headers={"User-Agent": AGENT})
    with urllib.request.urlopen(request, timeout=PATIENCE) as answer:
        return json.loads(answer.read().decode("utf-8"))


def find_city(name):
    """
    A city by its name: {name, country, latitude, longitude, timezone},
    or None when nothing by that name exists.
    """
    found = _get(GEOCODER, {"name": name, "count": 1, "language": "ru",
                            "format": "json"})
    results = found.get("results") or []
    if not results:
        return None
    first = results[0]
    return {"name": first.get("name") or name,
            "country": first.get("country") or "",
            "latitude": first["latitude"], "longitude": first["longitude"],
            "timezone": first.get("timezone") or "auto"}


def forecast(place):
    """Now and the rest of today, hour by hour, in the place's own time."""
    return _get(FORECAST, {
        "latitude": place["latitude"], "longitude": place["longitude"],
        "current": "temperature_2m,weather_code",
        "hourly": "precipitation_probability,weather_code",
        "timezone": place.get("timezone") or "auto",
        "forecast_days": 1,
    })
