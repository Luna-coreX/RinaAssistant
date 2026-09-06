# -*- coding: utf-8 -*-
"""
The settings schema: the meaning of the values, but not their appearance.

Plan item `4.0-E06a`; the decision is
[ADR 0006](../docs/adr/0006-settings-ownership.md).

The core owns the meaning: what type a value has, what it accepts, what it
depends on, whether it may be shown and when a change takes effect. The
shell owns the presentation: the labels, the grouping into sections, the
order, the search. The boundary runs not between "the form" and "the values"
but between **meaning and appearance**.

Why, briefly. Field labels are interface strings, and `4.0-F08` has already
decided that they live in the shell; a core that described the form would
take them for itself and quietly overturn that decision. The ten sections of
the settings screen are the work of `4.0-R04`, that is, a statement about
how a person sits down to set up a voice assistant, not a property of the
data.

But the reverse is untrue as well: only the core knows that `llm_model` is
meaningless while the model is off, and that an address outside `localhost`
sends conversations to somebody else's machine. Handing that to the shell
means keeping a second copy of the knowledge in another language, and it
will part company with the first in silence.

**The type and the default value are derived** rather than rewritten by
hand: they are already in `DEFAULTS`, and a second copy of them would part
company with the first. Written by hand is only what the defaults do not
show — the enumerations, the ranges, the dependencies, the secrecy and the
need for a restart.
"""

from dataclasses import dataclass
from typing import Any

from core.settings_store import DEFAULTS, GROUPS

#: What a default value's Python type is called in the protocol.
_TYPE_NAMES = {
    str: "string", bool: "boolean", int: "integer", float: "number",
    dict: "object", list: "array",
}


@dataclass(frozen=True)
class Constraint:
    """What the core knows about a value beyond its type."""

    choices: tuple[Any, ...] = ()
    low: float | None = None
    high: float | None = None
    #: A key whose being switched off makes this parameter meaningless.
    depends_on: str = ""
    #: Do not show in the open and do not write to the journal.
    secret: bool = False
    #: Takes effect only after a restart.
    restart_required: bool = False
    #: The key no longer takes part, but the data is not erased. The shell
    #: does not show it; there is nothing to delete from the store and no
    #: point in doing so.
    obsolete: bool = False
    #: The set of values is known to the core, but not in advance: which
    #: voices are installed, which engines are available. The shell asks for
    #: the list through `settings.options`.
    dynamic: bool = False
    #: The value is a path. What exactly to pick it with (a folder or a file
    #: dialogue) is the shell's decision; the core only says it is a path.
    format: str = ""
    #: A warning code, if the value is dangerous but permissible.
    warn_code: str = ""


#: Only what the defaults do not show. An empty entry here is not needed: a
#: key without constraints is described by its type and default, and that is
#: enough.
CONSTRAINTS: dict[str, Constraint] = {
    "volume": Constraint(low=0, high=100),
    "speed": Constraint(low=50, high=200),
    "wake_sensitivity": Constraint(low=0.0, high=1.0),
    "listen_seconds": Constraint(low=1, high=60),
    "llm_timeout": Constraint(low=1, high=600, depends_on="llm_enabled"),
    "log_level": Constraint(choices=("DEBUG", "INFO", "WARNING", "ERROR")),

    # The set of values is known to the core, but depends on what is
    # installed: which engines were assembled, which voices were found. That
    # cannot be expressed by a static enumeration — the shell will ask for
    # the list.
    "tts_engine": Constraint(dynamic=True),
    "stt_engine": Constraint(dynamic=True),
    "voice": Constraint(dynamic=True),
    "whisper_model": Constraint(dynamic=True),

    # Paths to models. What to pick them with is the shell's business; the
    # core says only that this is a path, not a name.
    # Which actions exist at all is known to the core
    # (`voice/hotkey_actions.py`): some of them are its own skills. Hotkeys
    # for them are assigned by the shell, because the keyboard is the system,
    # and in 4.0 the system is the shell's.
    "action_hotkeys": Constraint(dynamic=True),

    "vosk_model": Constraint(format="folder"),
    # The folder list consists of paths: that is enough for the shell to
    # offer a folder picker rather than a field where a path is typed by hand
    # with a typo.
    "program_folders": Constraint(format="folder"),
    "piper_model": Constraint(format="file"),
    "search_engine": Constraint(choices=("google", "yandex", "duckduckgo",
                                         "bing")),

    # The language model: three fields are meaningless while it is off.
    "llm_url": Constraint(depends_on="llm_enabled",
                          warn_code="llm.remote_address"),
    "llm_model": Constraint(depends_on="llm_enabled"),
    "llm_persona": Constraint(depends_on="llm_enabled"),

    # Recording the text of lines is a decision about privacy, and it has
    # force only when history is on.
    "log_texts": Constraint(depends_on="save_history"),

    # The finish changes on the fly: the two are equal, and a whole resource
    # dictionary is swapped rather than colours recomputed from a base one.
    # It needs no restart — and demanding one would be lying about how it is
    # built.
    "finish": Constraint(choices=("silver", "black")),

    # The language changes rarely and affects the whole window.
    # The languages are enumerated by the core: `core.i18n` knows the list,
    # and it also changes with which translations were assembled. A restart
    # is no longer needed — since 4.0-F08 the language is applied at once by
    # both sides: the core switches Rina's lines, the shell the interface's
    # words.
    "ui_language": Constraint(dynamic=True),

    # 3.1.0's five borrowed palettes. Replaced by two finishes (4.0-R08);
    # the values stay in the store but are not handed out.
    "theme": Constraint(obsolete=True),
    # The accent is back: `4.0-R08` replaced five palettes with two
    # finishes, but an accent is not a palette — it is one colour with two
    # duties, and every one of its variants is checked for contrast. The set
    # is enumerated by the shell: the variants depend on the finish, and the
    # finish is its business.
    "accent": Constraint(),

    # Internal: not settings but the state of the store.
    "config_version": Constraint(secret=True),
    "first_run": Constraint(secret=True),

    # The wake word in the singular is 3.1.0's form, a mirror of the first
    # of `wake_words`. The store writes it for compatibility; showing it next
    # to the list would mean offering a person one and the same thing to edit
    # twice and differently.
    "wake_word": Constraint(obsolete=True),
}


def type_of(key: str) -> str:
    """A value's type, from its default."""
    return _TYPE_NAMES.get(type(DEFAULTS.get(key)), "string")


def describe_key(key: str) -> dict[str, Any]:
    """The description of one key: type, default and everything known about it."""
    rule = CONSTRAINTS.get(key, Constraint())
    out: dict[str, Any] = {"type": type_of(key), "default": DEFAULTS.get(key)}
    if rule.choices:
        out["choices"] = list(rule.choices)
    if rule.low is not None:
        out["low"] = rule.low
    if rule.high is not None:
        out["high"] = rule.high
    if rule.depends_on:
        out["depends_on"] = rule.depends_on
    if rule.secret:
        out["secret"] = True
    if rule.restart_required:
        out["restart_required"] = True
    if rule.obsolete:
        out["obsolete"] = True
    if rule.dynamic:
        out["dynamic"] = True
    if rule.format:
        out["format"] = rule.format
    return out


#: What counts as a setting at all.
#:
#: The store keeps both settings and data in one file: commands, history,
#: reminders, the state of plugins. To the store these are one and the same —
#: a key and a value — but to a person they are not: "history" is not a
#: setting, and showing it as a field on the settings screen is meaningless.
#:
#: This came out when the settings screen was built for the first time: the
#: "Other" section held the history, the commands and the reminders. The
#: schema describes the **settings group**, not the whole file.
SETTABLE = tuple(GROUPS["settings"])


def describe(keys=None) -> dict[str, dict[str, Any]]:
    """The schema whole, or for the keys listed."""
    names = list(keys) if keys else list(SETTABLE)
    return {key: describe_key(key) for key in names if key in SETTABLE}


def options_for(key: str, settings) -> list[dict[str, Any]]:
    """
    Which values a key takes **right now**, on this machine.

    The core answers, because only it knows: which engines were assembled,
    which voices are installed. The shell cannot enumerate this — it has
    neither the models nor their catalogues.

    **A thing's name comes from where the thing lives.** "Vosk (offline)" is
    the engine's name, part of what the engine is, just as "Discord" is a
    program's name in the index. An interface string is "Activation words";
    that is still in the shell (`4.0-F08`). The boundary runs between the
    names of things and the words of the interface, not between processes.
    """
    from core.i18n import t as tr
    from voice import stt, tts

    def named(title):
        """
        The engine's name — in the person's language.

        The tables in `voice/tts.py` are written as literals; they are
        translated here, on the way out, for the same reason as the kinds of
        command: a table is keys, and the language is chosen in settings.
        """
        return tr(str(title))

    if key == "tts_engine":
        return [{"value": i, "title": named(t), "available": bool(a)}
                for i, t, a in tts.engine_choices()]
    if key == "stt_engine":
        return [{"value": i, "title": named(t), "available": bool(a)}
                for i, t, a in stt.engine_choices()]
    if key == "voice":
        engine = tts.get_engine(str(settings.get("tts_engine", "silent")))
        return [{"value": i, "title": named(t), "available": True}
                for i, t in engine.voices()]
    if key == "action_hotkeys":
        # Here "values" means what a hotkey can be assigned to, not the
        # hotkeys themselves: a person invents those, and they cannot be
        # enumerated.
        from voice.hotkey_actions import HOTKEY_ACTIONS
        return [{"value": action, "title": title, "available": True}
                for action, (title, _hint, _icon) in HOTKEY_ACTIONS.items()]
    if key == "ui_language":
        # The share of translation is deliberately not given as a number:
        # the core knows only its own half — Rina's lines — while the words
        # of the interface are translated by the shell, which counts them
        # itself (ADR 0007). One number for two halves would be a precision
        # that does not exist.
        from core.i18n import LANGUAGES, coverage
        return [{"value": name,
                 "title": (name if coverage(name) >= 0.99
                           else f"{name} — перевод неполный"),
                 "available": True}
                for name in LANGUAGES]
    if key == "whisper_model":
        # Whisper's list of models is fixed and known without installing
        # anything: these are names, not files that were found.
        return [{"value": name, "title": named(title), "available": True}
                for name, title in (("tiny", "tiny — самая быстрая"),
                                    ("base", "base — по умолчанию"),
                                    ("small", "small"),
                                    ("medium", "medium"),
                                    ("large", "large — самая точная"))]
    return []


def validate(key: str, value: Any, settings=None) -> tuple[bool, str, str]:
    """
    Check a value. Returns (accepted, code, explanation).

    The code comes from the `4.0-D05` catalogue, so that the shell branches
    on it rather than on the text. An empty code with accepted=True means
    "all is well"; a non-empty one means the value was accepted but is worth
    a warning.
    """
    if key not in SETTABLE:
        # Data lies in the store too but is not a setting: "history" is not
        # something one configures with a field.
        return False, "settings.unknown_key", f"Нет такой настройки: {key}."

    rule = CONSTRAINTS.get(key, Constraint())
    expected = type_of(key)
    actual = _TYPE_NAMES.get(type(value), "string")
    # bool is a subclass of int, and "true" instead of a number would pass in silence.
    if expected in ("integer", "number") and isinstance(value, bool):
        return False, "settings.invalid_value", \
            f"«{key}» ожидает число, а не логическое значение."
    if expected == "number" and actual == "integer":
        actual = "number"
    if actual != expected:
        return False, "settings.invalid_value", \
            f"«{key}» ожидает {expected}, получено {actual}."

    # A dynamic set is checked against what exists right now: the list
    # "which voices are installed" cannot be yesterday's. A dictionary is
    # taken out from under this rule: the enumeration says what its **keys**
    # are, not which whole value is permissible.
    if rule.dynamic and not isinstance(value, dict):
        allowed = {o["value"] for o in options_for(key, settings or {})}
        if allowed and value not in allowed:
            return False, "settings.invalid_value", \
                f"«{key}»: такого значения сейчас нет."

    if rule.choices and value not in rule.choices:
        return False, "settings.invalid_value", \
            f"«{key}» принимает только: {', '.join(map(str, rule.choices))}."
    if rule.low is not None and value < rule.low:
        return False, "settings.invalid_value", \
            f"«{key}» не может быть меньше {rule.low}."
    if rule.high is not None and value > rule.high:
        return False, "settings.invalid_value", \
            f"«{key}» не может быть больше {rule.high}."

    # Accepted, but worth a warning. This is the core's knowledge: only it
    # knows what this address is for and what goes out over it.
    if key == "llm_url" and isinstance(value, str) and value:
        host = value.split("//")[-1].split("/")[0].split(":")[0].lower()
        if host and host not in ("localhost", "127.0.0.1", "::1", "[::1]"):
            return True, "llm.remote_address", (
                "Адрес не локальный: тексты разговоров будут уходить "
                f"на {host}.")

    return True, "", ""
