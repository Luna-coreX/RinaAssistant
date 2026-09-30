# -*- coding: utf-8 -*-
"""
The arithmetic of the living background's colour, in one place.

Plan item `4.0b-A06`. The flow's palette depends on two things — the finish
and the accent — and its dimmed variant depends on a third. Which means
there are three places that need the same answer: the generator, which
writes the colours into the shell's resources; the contrast check, which has
to know every colour the flow can reach; and the design check.

**One implementation, not three.** A second implementation of a formula is a
divergence waiting for the first change to it, and it diverges silently:
both sides go on producing plausible colours, and only the person sees that
the check was measuring a palette the shell does not paint. That is the same
reason `sandbox.py` records what was stored rather than what was passed.

The shell does not compute any of this: it reads the colours it is given.
"""


def rgb(value):
    """`#1d2022` -> (29, 32, 34)."""
    head = value.lstrip("#")
    return tuple(int(head[at:at + 2], 16) for at in (0, 2, 4))


def hexed(channels):
    """(29, 32, 34) -> `#1d2022`."""
    return "#" + "".join(f"{max(0, min(255, round(c))):02x}" for c in channels)


def mix(one, two, amount):
    """Somewhere between two colours; 0 is the first, 1 is the second."""
    a, b = rgb(one), rgb(two)
    return hexed(x + (y - x) * amount for x, y in zip(a, b))


def _linear(channel):
    """One channel, straightened out of the display's curve."""
    value = channel / 255.0
    return (value / 12.92 if value <= 0.03928
            else ((value + 0.055) / 1.055) ** 2.4)


def _bent(value):
    """And back into it."""
    value = max(0.0, min(1.0, value))
    out = (value * 12.92 if value <= 0.0031308
           else 1.055 * value ** (1 / 2.4) - 0.055)
    return out * 255


def luminance(value):
    """WCAG relative luminance. The same one the contrast check uses."""
    red, green, blue = (_linear(c) for c in rgb(value))
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def at_luminance(value, wanted):
    """The same colour, moved to a given lightness."""
    have = luminance(value)
    if have <= 0.0001 or wanted <= 0.0001:
        return value
    factor = wanted / have
    return hexed(_bent(_linear(c) * factor) for c in rgb(value))


def tinted(ramp, accent, amount):
    """
    The flow's palette, carrying the accent.

    Two rules, and the second one is the whole reason this is not a plain
    blend.

    **The accent enters the light end and grows along the ramp.** That is
    what light does: a coloured source tints what it falls on brightly and
    leaves the shadows the colour of the material. An even tint would stop
    being a lit panel and become a panel painted another colour.

    **And it colours without lightening.** Every stop is put back at the
    lightness it had. Accents are bright — amber is `#f2731c` — and a plain
    blend towards one raised the light stops straight through the readability
    ceiling: twenty-seven of the thirty-six accent-and-finish pairs failed at
    once, all of them on the legends. Restoring the lightness keeps the
    thing the accent was for, which is hue, and gives up the thing it must
    not have, which is brightness. Nothing was loosened to make this pass.

    The darkest stop is left alone entirely — it is the ground the whole
    picture is measured against, and moving it would move everything.
    """
    if not ramp:
        return []
    last = len(ramp) - 1
    out = []
    for at, stop in enumerate(ramp):
        share = 0.0 if last == 0 else (at / last) ** 1.6
        blended = mix(stop, accent, amount * share)
        out.append(at_luminance(blended, luminance(stop)))
    return out


def dimmed(ramp, face, amount):
    """
    The same palette, calmed down — for the pages one reads on.

    Pulled towards the finish's own face rather than towards black or
    towards transparency: the calm version has to stay the same material,
    or the two halves of the window would look painted by different hands.
    """
    return [mix(stop, face, amount) for stop in ramp]


def every_ramp(finish):
    """
    Every palette this finish's flow can actually reach.

    Both the vivid and the calm variant, for every accent — because the
    contrast check has to hold for the colours a person can end up looking
    at, not for the one the author had set while writing it.
    """
    nebula = finish.get("nebula") or {}
    base = nebula.get("ramp") or []
    if not base:
        return {}
    face = finish["color"]["FACE"]
    dim = nebula.get("dim", 0.0)

    out = {}
    for name, accent in (finish.get("accents") or {}).items():
        vivid = tinted(base, accent["signal"], nebula.get("accent", 0.0))
        out[f"{name}"] = vivid
        out[f"{name}/тусклый"] = dimmed(vivid, face, dim)
    return out
