"""
The units, and the reading of a phrase into a sum.

Kept apart from the plugin on purpose: what a mile is has nothing to do
with tiles, actions or the plugin API, and a file that knows about both
is a file two different people have to read.
"""
import re

#: The units, by dimension: {what it is called: how many base units}.
#:
#: The base is the metre, the kilogram, the litre and the metre per
#: second. Which base does not matter — only that there is one per
#: dimension, so that anything converts to anything without a table of
#: pairs.
SCALES = {
    "длина": {
        ("м", "метр", "метра", "метры", "метров", "метрах",
         "metre", "meter", "m"): 1.0,
        ("км", "километр", "километра", "километры", "километров",
         "километрах", "km"): 1000.0,
        ("см", "сантиметр", "сантиметра", "сантиметры", "сантиметров",
         "сантиметрах", "cm"): 0.01,
        ("мм", "миллиметр", "миллиметра", "миллиметры", "миллиметров",
         "миллиметрах", "mm"): 0.001,
        ("миля", "мили", "миль", "милях", "mile", "miles", "mi"): 1609.344,
        ("фут", "фута", "футы", "футов", "футах",
         "foot", "feet", "ft"): 0.3048,
        ("дюйм", "дюйма", "дюймы", "дюймов", "дюймах",
         "inch", "inches", "in"): 0.0254,
        ("ярд", "ярда", "ярды", "ярдов", "ярдах", "yard", "yd"): 0.9144,
    },
    "масса": {
        ("кг", "килограмм", "килограмма", "килограммы", "килограммов",
         "килограммах", "kg"): 1.0,
        ("г", "грамм", "грамма", "граммы", "граммов", "граммах",
         "g"): 0.001,
        ("т", "тонна", "тонны", "тонн", "тоннах", "ton", "tonne"): 1000.0,
        ("фунт", "фунта", "фунты", "фунтов", "фунтах",
         "pound", "pounds", "lb"): 0.45359237,
        ("унция", "унции", "унций", "унциях",
         "ounce", "oz"): 0.028349523125,
    },
    "объём": {
        ("л", "литр", "литра", "литры", "литров", "литрах",
         "litre", "liter", "l"): 1.0,
        ("мл", "миллилитр", "миллилитра", "миллилитры", "миллилитров",
         "миллилитрах", "ml"): 0.001,
        ("галлон", "галлона", "галлоны", "галлонов", "галлонах",
         "gallon", "gal"): 3.785411784,
    },
    "скорость": {
        ("км/ч", "кмч", "kph", "km/h"): 1 / 3.6,
        ("м/с", "мс", "m/s", "mps"): 1.0,
        ("миль/ч", "mph", "mi/h"): 0.44704,
    },
}

#: How a unit is written in an answer.
#:
#: Short symbols, and that is not laziness. After a number a Russian
#: unit name has to agree — «3,11 мили», but «5,02 миль» — and a plugin
#: that guessed the case would get it wrong in front of the person
#: holding the answer. A symbol has no case.
SHOWN = {
    "м": "м", "км": "км", "см": "см", "мм": "мм",
    "миля": "mi", "фут": "ft", "дюйм": "in", "ярд": "yd",
    "кг": "кг", "г": "г", "т": "т", "фунт": "lb", "унция": "oz",
    "л": "л", "мл": "мл", "галлон": "gal",
    "км/ч": "км/ч", "м/с": "м/с", "миль/ч": "mph",
    "c": "°C", "f": "°F", "k": "K",
}

#: Temperature is not a scale but an offset, so it lives apart: nought
#: degrees Celsius is not nought of anything.
HEAT = {
    ("c", "°c", "цельсий", "цельсия", "цельсиях", "celsius"): "c",
    ("f", "°f", "фаренгейт", "фаренгейта", "фаренгейтах",
     "fahrenheit"): "f",
    ("k", "кельвин", "кельвина", "кельвинах", "kelvin"): "k",
}

#: «5 км в мили», «20 c to f», «3кг → фунты».
SAID = re.compile(
    r"^\s*(-?\d+(?:[.,]\d+)?)\s*([^\d]+?)\s+(?:в|во|to|in|→|->)\s+(.+?)\s*$",
    re.IGNORECASE)


def _canonical(word):
    """The unit this word names, and what kind of thing it measures."""
    word = word.strip().strip(".").lower().replace("ё", "е")
    for dimension, units in SCALES.items():
        for names in units:
            if word in names:
                return dimension, names[0]
    for names, name in HEAT.items():
        if word in names:
            return "температура", name
    return None, None


def convert(said):
    """
    Read a phrase and work out the answer.

    Returns the sentence to show, or a refusal saying what was not
    understood. A refusal that only says "no" leaves a person guessing
    which half of what they typed was wrong.
    """
    found = SAID.match(said or "")
    if not found:
        return None, "Не поняла. Например: «5 км в мили»."

    try:
        amount = float(found.group(1).replace(",", "."))
    except ValueError:
        return None, "Не поняла число."

    from_kind, from_unit = _canonical(found.group(2))
    to_kind, to_unit = _canonical(found.group(3))

    if from_unit is None:
        return None, f"Не знаю единицу «{found.group(2).strip()}»."
    if to_unit is None:
        return None, f"Не знаю единицу «{found.group(3).strip()}»."
    if from_kind != to_kind:
        # Named rather than declined: «Длина в масса не переводится» is
        # what a program says, not a person. Two nouns in the
        # nominative and a colon need no agreement at all.
        return None, f"Это разные величины: {from_kind} и {to_kind}."

    if from_kind == "температура":
        out = _heat(amount, from_unit, to_unit)
    else:
        units = SCALES[from_kind]
        factor = {names[0]: value for names, value in units.items()}
        out = amount * factor[from_unit] / factor[to_unit]

    return (f"{_number(amount)} {SHOWN[from_unit]} = "
            f"{_number(out)} {SHOWN[to_unit]}"), ""


def _heat(amount, out_of, into):
    """Through Celsius, because everything here has a formula to it."""
    celsius = {"c": lambda v: v,
               "f": lambda v: (v - 32) / 1.8,
               "k": lambda v: v - 273.15}[out_of](amount)
    return {"c": lambda v: v,
            "f": lambda v: v * 1.8 + 32,
            "k": lambda v: v + 273.15}[into](celsius)


def _number(value):
    """
    As many places as the number is worth, and a comma.

    Two places for an ordinary answer, more only when two would round it
    to nothing: «0,00 км» is not an answer, «0,0016 км» is.
    """
    for places in (2, 3, 4, 6):
        said = f"{value:.{places}f}"
        if float(said) != 0 or value == 0:
            break
    said = said.rstrip("0").rstrip(".")
    return (said or "0").replace(".", ",")
