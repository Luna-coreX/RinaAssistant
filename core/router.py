"""
The router: text -> intent. A pure function.

Plan item 4.0-B02. Before it, the pipeline decided and performed at the same
time: what the core had understood could be learned only from what it did.
Because of that the parse could neither be checked without side effects, nor
sent over the protocol, nor have a language model placed beside it.

The rules, without which there is no point:

    * The router launches nothing, says nothing, writes to no files and does
      not go to the network.
    * The router reads nothing itself: everything it needs to know about the
      world arrives in a RouterContext. So it can be called in a test
      without raising the application — and the golden suite checks
      precisely it.
    * It returns an Intent, not the text of an answer. How to voice that is
      the executor's business, and after 4.0-F08 the text is assembled in
      the core separately anyway.

The order of the steps repeats 3.1.0's pipeline literally
(docs/INVENTORY-3.1.0.md, §1) — otherwise the behaviour changes, and the
4.0-port boundary forbids that.

What the router does not yet decide: plugins and user commands. A plugin is
somebody else's code, and "would it take the phrase" is found out only by
running it; user commands are matched cleanly, but performing them is still
in the core. Both steps will move here along with 4.0-B03 and 4.0-B04. Until
then the core asks them before the router, exactly as before.
"""

from dataclasses import dataclass, field

from core.intent import Intent


# Consent and refusal for a dangerous action. They live here rather than in
# the core: this is part of parsing, and the router is obliged to work
# without raising the core.
# We require an explicit "yes" — tacit consent to shutting the PC down is
# inadmissible.
YES_WORDS = ("да", "давай", "подтверждаю", "точно", "выключай",
             "перезагружай", "усыпляй", "ага", "yes", "confirm")
NO_WORDS = ("нет", "отмена", "отмени", "не надо", "стоп", "no", "cancel")


@dataclass
class RouterContext:
    """
    Everything the router knows about the world. Read-only, no stores.

    Assembled by the calling side: by the core from the settings and the
    stores, by the runner by hand. That is exactly why the router is tested
    without the application.
    """

    #: The index of installed programs (a list of AppEntry).
    apps: list = field(default_factory=list)
    #: The learned associations "as it was said" -> a program.
    aliases: dict = field(default_factory=dict)
    #: The unclosed question — a dict of the form core.dialog.Question.to_dict().
    pending: dict = None
    #: The activation words.
    wake_words: tuple = ("рина",)
    #: Whether to require the wake word (the "always listen" mode).
    require_wake: bool = False
    #: Where the phrase came from: typed | voice | always.
    source: str = "typed"
    #: How many reminders are active right now — for list/cancel.
    reminders_active: int = 0
    #: Whether answering with a language model is switched on.
    llm_enabled: bool = False
    #: Whether to search the internet for what was not recognised.
    web_fallback: bool = True
    #: The words of consent and refusal for confirmations.
    yes_words: tuple = YES_WORDS
    no_words: tuple = NO_WORDS


def route(text, ctx=None):
    """Text -> Intent. Performs nothing."""
    ctx = ctx or RouterContext()

    if not text:
        return Intent("silence", stage="empty", text="")

    command = _strip_wake(text, ctx)
    if command is None:
        return Intent("silence", stage="wake", text=text)
    if not command:
        # The wake word sounded, there is no command. In "always listen"
        # mode we do not answer: Rina would hear her own answer and loop.
        if ctx.source == "always":
            return Intent("silence", stage="wake", text=text)
        return Intent("ask.wake", stage="wake", text=text)

    for stage in (_answer_to_question, _reminder, _system, _launch,
                  _builtin, _tail):
        intent = stage(command, ctx)
        if intent is not None:
            return intent.with_(text=command)

    return Intent("fallback.none", stage="tail", text=command)


# ---------------------------------------------------------------------------
def _strip_wake(text, ctx):
    """The command without the wake word. None means there was no activation."""
    if not ctx.require_wake:
        return text.strip()
    from voice.wake import strip_wake

    words = [w for w in (ctx.wake_words or ()) if w]
    if not words:
        return text.strip()
    return strip_wake(text, list(words))


def _answer_to_question(command, ctx):
    """Is the phrase an answer to a question asked earlier?"""
    pending = ctx.pending
    if not pending:
        return None

    kind = pending.get("kind")
    if kind in ("confirm_action", "confirm_command"):
        from voice.textmatch import normalize

        words = normalize(command).split()
        # Refusal is checked before consent — that is how 3.1.0 behaves, and
        # "no, go on" reads as a refusal (see the inventory, §2).
        if any(w in words for w in ctx.no_words):
            return Intent("cancelled", {"was": kind,
                                        "action": pending.get("action", "")},
                          stage="pending")
        if any(w in words for w in ctx.yes_words):
            # The confirmation from the question travels along with the
            # intent: without it the registry will reject the dangerous
            # action (4.0-C05).
            confirmation_id = pending.get("confirmation_id", "")
            if kind == "confirm_action":
                return Intent("system.action",
                              {"action": pending.get("action"),
                               "confirmation_id": confirmation_id},
                              stage="pending")
            return Intent("user_command",
                          {"command_id": pending.get("command_id", ""),
                           "confirmation_id": confirmation_id},
                          stage="pending")
        return None            # an unclear answer: the question is withdrawn, see the core

    if kind == "choose_app":
        from voice import app_index, app_launcher

        options = [app_index.AppEntry.from_dict(o)
                   for o in (pending.get("options") or [])]
        if not options:
            return None
        entry, cancelled = app_launcher.choose(command, options)
        if cancelled:
            return Intent("cancelled", {"was": kind}, stage="pending")
        if entry is None:
            return None
        return Intent("app.launch",
                      {"app": entry.name, "query": pending.get("query", "")},
                      stage="pending")

    return None


def _reminder(command, ctx):
    from voice import reminders

    parsed = reminders.parse(command)
    if parsed is None:
        return None

    if parsed.action == "list":
        return Intent("reminder.list",
                      {"empty": ctx.reminders_active == 0}, stage="reminders")
    if parsed.action == "cancel":
        return Intent("reminder.cancel",
                      {"empty": ctx.reminders_active == 0}, stage="reminders")

    args = {"kind": parsed.kind}
    if parsed.delay:
        args["seconds"] = parsed.delay
    if parsed.at:
        args["at"] = parsed.at
    if parsed.text:
        args["text"] = parsed.text
    return Intent("reminder.create", args, stage="reminders")


def _system(command, ctx):
    from voice import system_control

    action_id, needs_confirm = system_control.match_action(command)
    if not action_id:
        return None
    name = "system.confirm" if needs_confirm else "system.action"
    return Intent(name, {"action": action_id}, stage="system")


def _launch(command, ctx):
    from voice import app_launcher

    decision = app_launcher.decide(command, apps=ctx.apps,
                                   aliases=ctx.aliases)
    if decision is None:
        return None
    if decision.status == "launch":
        return Intent("app.launch", {"app": decision.entry.name},
                      stage="launcher")
    if decision.status == "ambiguous":
        # The options as dicts rather than objects: this is the question's
        # state, and it is obliged to survive being written to a file and
        # travelling over the protocol (4.0-B03).
        return Intent("app.ambiguous",
                      {"options": [e.to_dict() for e in decision.options],
                       "query": decision.query}, stage="launcher")
    return Intent("app.not_found", {"query": decision.query},
                  stage="launcher")


def _builtin(command, ctx):
    from voice import calculator, commands, websearch

    found = calculator.classify(command)
    if found:
        name, args = found
        return Intent(name, args, stage="builtin")

    query = websearch.extract_query(command)
    if query:
        return Intent("websearch", {"query": query}, stage="builtin")

    topic = commands.match_answer(command.lower().strip())
    if topic:
        return Intent("builtin.answer", {"topic": topic}, stage="builtin")

    return None


def _tail(command, ctx):
    """The pipeline's tail: the model, then a search, then a refusal."""
    if ctx.llm_enabled:
        # The router does not ask the model — that is the network and
        # seconds. It only names the intent; the executor asks.
        return Intent("llm.answer", stage="tail", confidence=0.5)

    # In "always listen" mode we do not search: noise and chance speech land
    # there, and a browser must not be opened on them.
    if ctx.web_fallback and ctx.source != "always":
        return Intent("fallback.search", {"query": command}, stage="tail")

    return None
