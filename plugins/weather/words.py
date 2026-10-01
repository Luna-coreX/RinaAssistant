"""
The weather in words (`4.0b-K06`).

Pure functions over what the source returned, so they can be checked
without a network. Two forms of one answer: `aloud` is what Rina says —
«На улице прохладно: 6 градусов, морось. Часам к 15 обещают дождь. Зонт
пригодится.» — and `now_said` is the value the "find out" step keeps, which
stands **inside** a sentence a person wrote: «На улице {погода}». Both come
in several variants, so the same weather is not said word for word every
morning.
"""
import re

from plugins.api import vary as pick

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

#: The home screen's picture for a WMO code (`plugins/page_spec.py::ICONS`).
PICTURES = {0: "clear", 1: "partly", 2: "partly", 3: "cloudy",
            45: "fog", 48: "fog",
            51: "drizzle", 53: "drizzle", 55: "drizzle", 56: "drizzle",
            57: "drizzle",
            61: "rain", 63: "rain", 65: "rain", 66: "rain", 67: "rain",
            80: "rain", 81: "rain", 82: "rain",
            71: "snow", 73: "snow", 75: "snow", 77: "snow", 85: "snow",
            86: "snow", 95: "storm", 96: "storm", 99: "storm"}


def icon(current):
    """The picture for the weather now — the moon instead of the sun at night."""
    name = PICTURES.get(current.get("weather_code"), "cloudy")
    if current.get("is_day") == 0 and name in ("clear", "partly"):
        name += "_night"
    return name


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


def _state(data):
    """
    What the rest of the day holds: (kind, hour, noun, missing, until).

    `kind` is "dry", "likely" or "possible"; "stopping" — it is raining (or
    snowing) now and nothing more is expected; "going on" — it is falling
    now and the forecast says it will go on, where «скоро обещают дождь»
    would promise what is already outside the window; `hour` is then when
    it should stop, or None for not before the evening. Counted on the place's
    own clock — the forecast comes in the city's local time — so a person
    in another time zone hears about that city's evening, not their own.
    Late in the day "the evening" is over and the horizon becomes the night.
    """
    current = data.get("current") or {}
    now = current.get("time", "")
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

    snowy = (any(code in SNOW for _h, _p, code in window)
             or current.get("weather_code") in SNOW)
    noun, missing = ("снег", "снега") if snowy else ("дождь", "дождя")

    known = [(h, p) for h, p, _c in window if p is not None]
    falling = (current.get("weather_code") or 0) >= 51
    later = [p for h, p in known if h > hour]
    if falling and later and max(later) < POSSIBLE:
        return "stopping", hour, noun, missing, until
    if not known or max(p for _h, p in known) < POSSIBLE:
        return "dry", hour, noun, missing, until
    likely = next((h for h, p in known if p >= LIKELY), None)
    if likely is not None and likely <= hour and falling:
        stop = next((h for h, p in known if h > hour and p < POSSIBLE), None)
        return "going on", stop, noun, missing, until
    if likely is not None:
        return "likely", (None if likely <= hour else likely), noun, missing, until
    possible = next(h for h, p in known if p >= POSSIBLE)
    return "possible", (None if possible <= hour else possible), noun, missing, until


def outlook(data):
    """Will it rain (or snow) before the evening, said the way a person says it."""
    kind, at, noun, missing, until = _state(data)
    # What is falling now is already named by the sky («дождь, 6 градусов»),
    # so these do not name it again: «стихнет», not «дождь закончится».
    if kind == "stopping":
        return pick(f"дальше {until} {missing} не обещают",
                    "скоро должно стихнуть")
    if kind == "going on":
        if at is None:
            return pick(f"{until} не утихнет", f"и так {until}")
        return pick(f"к {at}:00 должно стихнуть",
                    f"стихнуть должно часам к {at}")
    if kind == "dry":
        return pick(f"{missing} {until} не обещают",
                    f"{until} обойдётся без {missing}",
                    f"{until} {missing} не ждут")
    if kind == "likely":
        if at is None:
            return pick(f"скоро обещают {noun}", f"вот-вот пойдёт {noun}")
        return pick(f"к {at}:00 обещают {noun}",
                    f"часам к {at} обещают {noun}",
                    f"ближе к {at}:00 пойдёт {noun}")
    if at is None:
        return pick(f"возможен {noun}", f"может пойти {noun}")
    return pick(f"к {at}:00 возможен {noun}",
                f"к {at}:00 может пойти {noun}",
                f"после {at}:00 не исключён {noun}")


def feel(value):
    """How the temperature feels, in a word or two."""
    n = int(round(float(value)))
    if n <= -20:
        return pick("сильный мороз", "лютый мороз")
    if n <= -5:
        return pick("мороз", "морозно")
    if n <= -2:
        return pick("небольшой мороз", "морозец")
    if n <= 7:
        return pick("холодно", "зябко")
    if n <= 14:
        return pick("прохладно", "свежо")
    if n <= 21:
        return pick("тепло", "приятно")
    if n <= 27:
        return pick("тепло", "по-летнему тепло")
    return pick("жарко", "настоящая жара")


def advice(data):
    """A word of advice when the day calls for one — or nothing."""
    current = data.get("current") or {}
    kind, _at, noun, _missing, _until = _state(data)
    wet = kind in ("likely", "going on", "stopping") or (
        (current.get("weather_code") or 0) >= 51 and kind != "dry")
    if wet and noun == "дождь":
        return pick("Зонт пригодится.", "Лучше взять зонт.",
                    "Без зонта лучше не выходить.")
    if wet:
        return pick("На дорогах может быть скользко.", "Одевайся теплее.")
    if kind == "possible" and noun == "дождь":
        return pick("Зонт на всякий случай не помешает.",
                    "Можно захватить зонт — на всякий случай.")
    temperature = current.get("temperature_2m")
    if temperature is None:
        return ""
    if temperature <= -10:
        return pick("Одевайся теплее.", "Оденься потеплее.")
    if temperature >= 28:
        return pick("Не забудь воду.", "Лучше держаться в тени.")
    return ""


def _capital(text):
    return text[:1].upper() + text[1:]


def now_said(data):
    """
    The value the "find out" step keeps: it stands inside a sentence a
    person wrote — «На улице {погода}» → «На улице 12 градусов, пасмурно,
    дождя до вечера не обещают».
    """
    current = data.get("current") or {}
    sky = SKY.get(current.get("weather_code"), "")
    temperature = current.get("temperature_2m")
    if temperature is None:
        return ", ".join(part for part in (sky, outlook(data)) if part)
    deg = degrees(temperature)
    form = pick("plain", "and", "feel")
    if form == "and" and sky:
        return f"{deg} и {sky}, {outlook(data)}"
    if form == "feel" and sky:
        return f"{feel(temperature)}, {deg}, {sky}; {outlook(data)}"
    return ", ".join(part for part in (deg, sky, outlook(data)) if part)


def aloud(data):
    """
    The weather said aloud, the way a person says it — in one of several
    ways, with a word of advice when the day calls for one.

    «На улице прохладно: 6 градусов, морось. Часам к 15 обещают дождь.
    Зонт пригодится.»
    """
    current = data.get("current") or {}
    sky = SKY.get(current.get("weather_code"), "")
    temperature = current.get("temperature_2m")
    ahead = _capital(outlook(data)) + "."
    tip = advice(data)
    if temperature is None or not sky:
        head = _capital(now_said(data)) + "."
        return " ".join(part for part in (head, tip) if part)
    deg = degrees(temperature)
    head = pick(f"Сейчас {deg}, {sky}.",
                f"На улице {feel(temperature)}: {deg}, {sky}.",
                f"{_capital(sky)}, {deg} — {feel(temperature)}.",
                f"За окном {sky}, {deg}.")
    return " ".join(part for part in (head, ahead, tip) if part)


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
