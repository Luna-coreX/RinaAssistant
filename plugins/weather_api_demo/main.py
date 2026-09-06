"""Minimal API v4 external-API demo plugin.

Uses Open-Meteo's geocoding and forecast APIs. No API key is required.
"""

from plugins.api import Plugin, PluginTool
from core.tools import Param
import json
from urllib.parse import quote
from urllib.request import Request, urlopen


class WeatherApiDemo(Plugin):
    def tools(self):
        return [
            PluginTool(
                name="current_weather",
                summary="Get current weather for a city from Open-Meteo",
                params=(
                    Param("city", "string", "City name", required=True),
                ),
                permissions=("network.external",),
                confirm_required=False,
            )
        ]

    def on_command(self, text: str) -> bool:
        # Keep command handling deliberately simple: the tool path is the
        # actual API-v4 demonstration; this hook is only a manual smoke test.
        prefix = "погода в "
        if text.lower().startswith(prefix):
            city = text[len(prefix):].strip()
            if city:
                try:
                    self.respond(self._weather(city))
                except Exception as exc:
                    self.log(f"Weather API error: {exc}")
                    self.respond("Не удалось получить погоду.")
                return True
        return False

    def _get_json(self, url: str):
        request = Request(
            url,
            headers={"User-Agent": "RinaAssistant/4.0 Weather API Demo"},
        )
        with urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))

    def _weather(self, city: str) -> str:
        geo = self._get_json(
            "https://geocoding-api.open-meteo.com/v1/search?name="
            + quote(city)
            + "&count=1&language=en&format=json"
        )
        results = geo.get("results") or []
        if not results:
            return f"Город не найден: {city}"

        place = results[0]
        lat = place["latitude"]
        lon = place["longitude"]
        name = place.get("name", city)
        forecast = self._get_json(
            "https://api.open-meteo.com/v1/forecast?latitude="
            + str(lat)
            + "&longitude="
            + str(lon)
            + "&current=temperature_2m,relative_humidity_2m,weather_code"
            + "&timezone=auto"
        )
        current = forecast.get("current", {})
        temp = current.get("temperature_2m")
        humidity = current.get("relative_humidity_2m")
        return f"{name}: {temp}°C, влажность {humidity}%"
