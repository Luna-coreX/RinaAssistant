# -*- coding: utf-8 -*-
"""
4.0b-C02: hostile input — commands, plugin manifests, paths, protocol.

**"It did not crash" is not an assertion.** A parser that swallows everything
and returns `None` passes that, and so does one that quietly turns a hostile
card into a runnable action. So every front here has an invariant of its own
on top of not falling over: what comes out is either a **declared** refusal or
a value that satisfies the promise made about it elsewhere.

**The corpus is generated, and it is the same corpus every time.** Seeded from
a constant: a fuzz set that differs run to run reddens on somebody else's
machine and greens on yours, and the first thing anybody does with such a
suite is stop believing it. Growing it means raising the seed count or adding
a primitive, deliberately, in a commit that says so.

**Note on the plan.** The item says the ground already exists — a set of some
600 hostile inputs from 3.0.0, to be carried over. It is not in this
repository: not in `archive/3.1.0-app`, not in the history, nowhere under
`tools`. So this is written rather than ported, and the plan is corrected to
say so. Claiming a heritage that cannot be produced is how a suite comes to
be trusted for the wrong reason.
"""
import io
import json
import os
import random
import sys

sys.path.insert(0, r"C:\DevStation\PCDev\DesktopApps\RinaAssistant")
sys.path.insert(0, os.path.join(
    r"C:\DevStation\PCDev\DesktopApps\RinaAssistant", "tools"))

from console import use_utf8

use_utf8()

fails = 0


def check(label, cond, detail=""):
    global fails
    if not cond:
        fails += 1
    print(("OK   " if cond else "FAIL "), label, detail)


# ---------------------------------------------------------------------------
# The corpus
# ---------------------------------------------------------------------------
#: The pieces hostile inputs are built from. Each is here because it has
#: broken something somewhere, not because it looks alarming.
PRIMITIVES = [
    "", " ", "\t", "\n", "\r\n", "\x00", "\x00\x00", "\x1b[31m",
    "../", "..\\", "../../../etc/passwd", "C:\\Windows\\System32",
    "\\\\?\\C:\\", "\\\\server\\share", "con", "nul", "prn",
    "%s%s%s", "{0}{1}", "{}", "${HOME}", "`whoami`", "$(id)",
    "'; DROP TABLE calls; --", '" OR "1"="1',
    "<script>alert(1)</script>", "&lt;", "&#x41;",
    "\ufeff", "\u202e", "\u0000", "\u200b", "\U0001f4a9",
    "й" * 5000, "a" * 100000, "0" * 40,
    "-1", "1e308", "NaN", "Infinity", "-0",
    "true", "null", "undefined", "[]", "{}",
    "/", "//", "\\", ":", "::", "*", "?", "|", ">", "<",
]

#: Values of the wrong shape entirely. A field that expects a string gets a
#: list; one that expects a list gets a number.
WRONG_SHAPES = [
    None, True, False, 0, -1, 3.5, 10 ** 30, [], {}, [[]], {"a": {"b": {}}},
    [1, 2, 3], {"": ""}, [None], float("inf"),
]


def corpus(seed=4, size=600):
    """
    The hostile inputs, the same ones every run.

    Deep nesting is built rather than written out: a list two hundred levels
    deep is what a recursive parser dies on, and it is not something one
    types into a literal.
    """
    dice = random.Random(seed)
    out = list(PRIMITIVES) + list(WRONG_SHAPES)

    deep = []
    cursor = deep
    for _ in range(200):
        nest = []
        cursor.append(nest)
        cursor = nest
    out.append(deep)
    out.append({"steps": deep})

    while len(out) < size:
        kind = dice.randrange(5)
        if kind == 0:
            out.append("".join(dice.choice(PRIMITIVES)
                               for _ in range(dice.randrange(1, 5))))
        elif kind == 1:
            out.append(dice.choice(WRONG_SHAPES))
        elif kind == 2:
            out.append({dice.choice(PRIMITIVES): dice.choice(WRONG_SHAPES)})
        elif kind == 3:
            out.append([dice.choice(PRIMITIVES)
                        for _ in range(dice.randrange(0, 6))])
        else:
            out.append("".join(chr(dice.randrange(1, 0x2FFF))
                               for _ in range(dice.randrange(0, 40))))
    return out


HOSTILE = corpus()
print(f"враждебных вводов в наборе: {len(HOSTILE)}")
print()


# ---------------------------------------------------------------------------
# 1. Protocol envelopes
# ---------------------------------------------------------------------------
#
# The promise: a message either becomes an `Envelope` or is refused with a
# **declared** code. Anything else — a `KeyError`, a `TypeError`, a
# `RecursionError` — is a way for the other side to end the conversation by
# sending nonsense, and the whole point of the frame is that it cannot.
from core.wire.envelope import decode
from core.wire.errors import CATALOGUE, ProtocolFault

undeclared = []
for at, item in enumerate(HOSTILE):
    for raw in (
        item if isinstance(item, bytes) else None,
        str(item).encode("utf-8", "surrogatepass"),
        json.dumps(item, default=str).encode("utf-8"),
    ):
        if raw is None:
            continue
        try:
            decode(raw)
        except ProtocolFault as fault:
            code = getattr(getattr(fault, "error", None), "code", None) \
                or getattr(fault, "code", None) \
                or str(fault)
            if code not in CATALOGUE:
                undeclared.append((at, "код вне каталога", code))
        except RecursionError:
            undeclared.append((at, "RecursionError", repr(raw[:40])))
        except Exception as e:
            undeclared.append((at, type(e).__name__, repr(raw[:40])))

check("конверт: враждебное либо разбирается, либо отказано объявленным кодом",
      undeclared == [], f"| {undeclared[:4]} (всего {len(undeclared)})")

# And a well-formed envelope still gets through: a decoder that refused
# everything would satisfy the assertion above and nothing else.
good = json.dumps({
    "v": 1, "type": "request", "id": "req_1", "timestamp": 0,
    "trace_id": "tr_1", "payload": {}, "method": "settings.get",
}).encode("utf-8")
try:
    decode(good)
    passes = True
except Exception as e:
    passes = False
check("и правильный конверт по-прежнему проходит", passes)


# ---------------------------------------------------------------------------
# 2. Imported commands
# ---------------------------------------------------------------------------
#
# The promise (T-18): what comes in arrives switched off, of a known kind,
# within the limits. A card that got through as `system`/`shutdown` would be
# somebody else's file able to turn the machine off.
from core.data_transfer import (FORMAT_VERSION, KIND_COMMANDS,
                                TransferError, commands_from_data)
from voice.user_commands import COMMAND_TYPES, SYSTEM_ACTIONS

known_types = {t for t, *_ in COMMAND_TYPES} | {"pause"}
known_actions = {a for a, _ in SYSTEM_ACTIONS}

broke, wrong = [], []
for at, item in enumerate(HOSTILE):
    for shape in (
        {"kind": KIND_COMMANDS, "format": FORMAT_VERSION,
         "payload": {"commands": [item] if isinstance(item, dict) else item}},
        {"kind": KIND_COMMANDS, "format": FORMAT_VERSION,
         "payload": {"commands": [{"type": item, "target": item,
                                   "triggers": [item], "steps": [item]}]}},
        item,
    ):
        try:
            cards = commands_from_data(shape)
        except TransferError:
            continue
        except Exception as e:
            broke.append((at, type(e).__name__))
            continue
        for card in cards:
            if card.get("enabled"):
                wrong.append((at, "приехало включённым"))
            if card.get("type") not in known_types:
                wrong.append((at, f"вид {card.get('type')!r}"))
            if (card.get("type") == "system"
                    and card.get("target") not in known_actions):
                wrong.append((at, f"действие {card.get('target')!r}"))
            if len(str(card.get("target", ""))) > 1000:
                wrong.append((at, "цель длиннее предела"))
            if len(card.get("steps") or []) > 50:
                wrong.append((at, "шагов больше предела"))

check("команды: враждебный файл не роняет разбор", broke == [],
      f"| {broke[:4]} (всего {len(broke)})")
check("команды: ничто не проезжает включённым или незнакомым видом",
      wrong == [], f"| {wrong[:4]} (всего {len(wrong)})")


# ---------------------------------------------------------------------------
# 3. Plugin manifests and paths
# ---------------------------------------------------------------------------
#
# The promise (T-10): a name is either refused or becomes something whose
# path lands directly inside the plugins directory.
from plugins.manager import PluginInstallError, _safe_plugin_id, plugins_dir

base = os.path.abspath(plugins_dir())
escaped, exploded = [], []
for at, item in enumerate(HOSTILE):
    try:
        made = _safe_plugin_id(item)
    except PluginInstallError:
        continue
    except Exception as e:
        exploded.append((at, type(e).__name__))
        continue
    try:
        where = os.path.abspath(os.path.join(base, made))
    except Exception as e:
        exploded.append((at, "join: " + type(e).__name__))
        continue
    if os.path.dirname(where) != base or where == base:
        escaped.append((at, where[:80]))

check("плагины: имя из чужого архива не роняет разбор", exploded == [],
      f"| {exploded[:4]} (всего {len(exploded)})")
check("плагины: путь установки не выходит из каталога", escaped == [],
      f"| {escaped[:4]} (всего {len(escaped)})")

# Windows device names, caught by name rather than by the shape of the
# path they produce. The fuzz set found `nul` this way: it passed the
# pattern — letters and nothing else — and `abspath` turned the result
# into a device path. Only `nul` bends the path like that; `con`, `prn`
# and `com1` come out looking like ordinary folders and are devices just
# the same, so the shape of a path cannot be what catches them.
devices = []
for name in ["nul", "con", "prn", "aux", "com1", "lpt9", "NUL", "Con",
             "nul.txt", "com1.plugin"]:
    try:
        _safe_plugin_id(name)
        devices.append(name)
    except PluginInstallError:
        pass
check("плагины: имя устройства Windows не становится плагином",
      devices == [], f"| прошло {devices}")


# ---------------------------------------------------------------------------
# 4. Phrases into the router
# ---------------------------------------------------------------------------
#
# The way hostile text actually arrives: recognised speech. The promise is
# that a phrase always becomes a **declared** intent — the catalogue in
# `core/intent.py` is checked on construction, so an undeclared name raises,
# and a phrase must never be able to make that happen.
from core.intent import UnknownIntent
from core.router import RouterContext, route

ctx = RouterContext()
fell = []
for at, item in enumerate(HOSTILE):
    if not isinstance(item, str):
        continue
    # The huge ones separately below: a hundred thousand characters through
    # every stage is slow, and slowness here would make the suite unrunnable
    # rather than untrue.
    if len(item) > 5000:
        continue
    try:
        intent = route(item, ctx)
        if intent is None or not getattr(intent, "name", ""):
            fell.append((at, "пустое намерение"))
    except UnknownIntent as e:
        fell.append((at, "необъявленное намерение: " + str(e)))
    except Exception as e:
        fell.append((at, type(e).__name__ + ": " + str(e)[:60]))

check("разбор фразы: враждебный текст не роняет ступени", fell == [],
      f"| {fell[:4]} (всего {len(fell)})")

# The long ones, on their own, because length is its own kind of hostile.
long_fell = []
for text in ("й" * 5000, "a" * 100000, " " * 20000, "\x00" * 1000):
    try:
        route(text, ctx)
    except Exception as e:
        long_fell.append((len(text), type(e).__name__))
check("разбор фразы: длина сама по себе тоже не роняет", long_fell == [],
      f"| {long_fell}")


print()
print("ИТОГО ошибок:", fails)
sys.exit(1 if fails else 0)
