"""
The weather in words (`4.0b-K06`).

Pure functions over what the source returned, so they can be checked
without a network. The answer is written to stand **inside** a sentence a
person wrote: «На улице {погода}» → «На улице 12 градусов, пасмурно, дождя
до вечера не обещают». That is the plugin's main use in a command, and an
answer that began «Погода в Казани:» would not fit anywhere but alone.
"""
import re

#: What the sky is doing, by the WMO code Open-Meteo reports.
SKY = {
    0: "ясно", 1: "почти ясно", 2: "переменная облачность", 3: "пасмурно",
    45: "туман", 48: "туман с изморозью",
    51: "морось", 53: "морось", 55: "сильная морось",
    56: "ледяная морось", 57: "ледяная морось",
    61: "небольшой дождь", 63: "дождь", 65: "сильный дождь",
    66: "ледяной дождь", 67: "ледяной дождь",
    71: "небольшой снег", 73: "снег", 75: "сильный снег", 77: "снежная крупа",
    80: "ливень", 81: "ливень", 82: "сильный ливень",
    85: "снегопад", 86: "сильный снегопад",
    95: "гроза", 96: "гроза с градом", 99: "гроза с градом",
}

#: The codes that fall as snow rather than rain.
SNOW = frozenset({71, 73, 75, 77, 85, 86})

#: Below this chance of precipitation nothing is promised; at or above
#: `LIKELY` it is promised, and in between it is possible. Two thresholds
#: rather than one, because «обещают дождь» at a 35 % chance is a promise
#: the forecast did not make.
POSSIBLE = 30
LIKELY = 60

#: The questions the plugin answers by itself, whole. A narrow set on
#: purpose: plugins hear a phrase before the built-in commands do, and one
#: that took every phrase with «погод» in it would take «поищи погоду в
#: Москве» away from the search.
QUESTIONS = frozenset({
    "погода", "какая погода", "какая сегодня погода", "какая погода сегодня",
    "какая погода на улице", "какая на улице погода", "что на улице",
    "что с погодой", "погода на сегодня", "будет ли дождь",
    "будет ли сегодня дождь", "нужен ли зонт", "брать ли зонт",
    "what is the weather", "what s the weather", "weather",
})


def asks(text):
    """Is the phrase one of the questions about the weather?"""
    words = re.findall(r"\w+", str(text or "").lower().replace("ё", "е"))
    return " ".join(words) in QUESTIONS


def plural(n, one, few, many):
    """The Russian form for a count: «1 градус», «2 градуса», «5 градусов»."""
    n = abs(int(n))
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def degrees(value):
    """«12 градусов», «минус 3 градуса», «ноль градусов»."""
    n = int(round(float(value)))
    if n == 0:
        return "ноль градусов"
    word = plural(n, "градус", "градуса", "градусов")
    return f"минус {abs(n)} {word}" if n < 0 else f"{n} {word}"


def _hour(stamp):
    """The hour of an ISO local time: «2026-10-01T06:30» → 6."""
    try:
        return int(str(stamp)[11:13])
    except ValueError:
        return -1


def outlook(data):
    """
    Will it rain (or snow) before the evening, said the way a person says it.

    Counted on the place's own clock — the forecast comes in the city's
    local time — so a person in another time zone hears about that city's
    evening, not their own. Late in the day "the evening" is over and the
    horizon becomes the night.
    """
    now = (data.get("current") or {}).get("time", "")
    today, hour = str(now)[:10], _hour(now)
    hourly = data.get("hourly") or {}
    times = hourly.get("time") or []
    chances = hourly.get("precipitation_probability") or []
    codes = hourly.get("weather_code") or []

    until, end = ("до вечера", 21) if hour < 18 else ("до ночи", 23)
    window = [(_hour(t), chances[i] if i < len(chances) else None,
               codes[i] if i < len(codes) else None)
              for i, t in enumerate(times)
              if str(t)[:10] == today and hour <= _hour(t) <= end]

    snowy = any(code in SNOW for _h, _p, code in window) \
        or (data.get("current") or {}).get("weather_code") in SNOW
    noun, missing = ("снег", "снега") if snowy else ("дождь", "дождя")

    known = [(h, p) for h, p, _c in window if p is not None]
    if not known or max(p for _h, p in known) < POSSIBLE:
        return f"{missing} {until} не обещают"
    likely = next((h for h, p in known if p >= LIKELY), None)
    if likely is not None:
        return (f"скоро обещают {noun}" if likely <= hour
                else f"к {likely}:00 обещают {noun}")
    possible = next(h for h, p in known if p >= POSSIBLE)
    return (f"возможен {noun}" if possible <= hour
            else f"к {possible}:00 возможен {noun}")


def now_said(data):
    """
    The answer that goes into a sentence: temperature, sky, the outlook.

    «12 градусов, пасмурно, дождя до вечера не обещают».
    """
    current = data.get("current") or {}
    parts = []
    if current.get("temperature_2m") is not None:
        parts.append(degrees(current["temperature_2m"]))
    sky = SKY.get(current.get("weather_code"))
    if sky:
        parts.append(sky)
    parts.append(outlook(data))
    return ", ".join(parts)


def as_of(data):
    """When the data is for, on the place's clock: «6:30»."""
    stamp = str((data.get("current") or {}).get("time", ""))
    if len(stamp) < 16:
        return ""
    return f"{int(stamp[11:13])}:{stamp[14:16]}"


def ago(seconds):
    """«только что», «12 минут назад», «2 часа назад»."""
    seconds = max(0, int(seconds))
    if seconds < 90:
        return "только что"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} {plural(minutes, 'минуту', 'минуты', 'минут')} назад"
    hours = minutes // 60
    return f"{hours} {plural(hours, 'час', 'часа', 'часов')} назад"
