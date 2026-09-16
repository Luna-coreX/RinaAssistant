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

import re
from dataclasses import dataclass, field

from core import apps as apps_mod
from voice import todo as todo_mod
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
    #: Whether the microphone was open on Rina's own initiative.
    #:
    #: **Three rules below used to ask `source == "always"`, and all three
    #: were dead.** That name is passed by the 3.1.0 path, where the core
    #: opened the microphone itself; since `4.0-G` the sound arrives from
    #: the shell and calls itself `voice` whichever mode it is in. So the
    #: rule "do not search the internet for chance speech" had never once
    #: fired in the running program, and an assistant with an open
    #: microphone answered a web search to every noise in the room —
    #: which is exactly what a person met.
    #:
    #: A fact, not a label. The name of a source says where a phrase came
    #: in, and these rules are about something else: whether anybody meant
    #: to say it.
    unbidden: bool = False
    #: How many reminders are active right now — for list/cancel.
    reminders_active: int = 0
    #: Whether answering with a language model is switched on.
    llm_enabled: bool = False
    #: Whether to search the internet for what was not recognised.
    web_fallback: bool = True
    #: The words of consent and refusal for confirmations.
    yes_words: tuple = YES_WORDS
    no_words: tuple = NO_WORDS

    #: What was last asked to be launched, as the person said it (4.0b-A04).
    #:
    #: Needed by a correction: "нет, я имел в виду Chrome" says what was
    #: meant and not what was asked for. Without this the correction has
    #: nothing to attach the lesson to.
    #:
    #: It is a phrase rather than a program: what is being taught is the
    #: word the person uses, and it is that word which will be said next
    #: time.
    last_launch_query: str = ""

    #: Everything on the list the words could mean — a list, not one.
    #: The list lives in the core and the router is obliged to work
    #: without it, hence a way to ask rather than the list itself.
    #:
    #: A list and not one thing: which of several is meant is the
    #: person's to say (`4.0b-E06`), and a finder that returns the first
    #: takes that decision quietly.
    todo_find: object = None


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
        if ctx.unbidden:
            return Intent("silence", stage="wake", text=text)
        return Intent("ask.wake", stage="wake", text=text)

    # `_teach` stands before `_launch` and after everything else: the only
    # stage it has to beat is launching. "Когда я говорю «код», открывай VS
    # Code" contains "открывай VS Code", and the launch parsing would take
    # the phrase for itself, starting the editor instead of learning the
    # rule.
    #
    # And after `_answer_to_question`, because "no" while a question is
    # pending stays a refusal. A correction comes when there is no
    # question: Rina has already launched the wrong thing and is being
    # corrected after the fact.
    # `_why` after the pending question and before everything else: "why"
    # while a question is on the table is still not an answer to it, and
    # before the rest because no other stage wants the word — but it is
    # cheap to parse and definite, and a phrase it does not take falls
    # through untouched.
    for stage in (_answer_to_question, _why, _todo, _reminder, _system,
                  _teach, _launch, _builtin, _tail):
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

    if kind == "offer_setting":
        from voice.textmatch import normalize

        words = normalize(command).split()
        # Refusal before consent, as everywhere here: "нет, не надо" reads
        # as a refusal (inventory, §2).
        if any(w in words for w in ctx.no_words):
            return Intent("cancelled", {"was": kind}, stage="pending")
        if any(w in words for w in ctx.yes_words):
            return Intent("offer.accepted",
                          {"key": pending.get("setting_key", ""),
                           "value": pending.get("setting_value", ""),
                           "about": pending.get("query", "")},
                          stage="pending")
        return None            # an unclear answer withdraws the question

    if kind == "choose_todo":
        from voice.textmatch import pick

        options = list(pending.get("options") or [])
        if not options:
            return None
        index, cancelled = pick(command, [o.get("text", "") for o in options])
        if cancelled:
            return Intent("cancelled", {"was": kind}, stage="pending")
        if index is None:
            return None
        return Intent("todo.done",
                      {"todo_id": options[index].get("id", ""),
                       "text": options[index].get("text", "")},
                      stage="pending")

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
    text = parsed.text

    # A reminder bound to a program (`4.0b-A03`).
    if parsed.when_app:
        entry, leftover, found, asked = _when_app(parsed.when_app, ctx)
        if entry is None:
            if len(found) > 1:
                return Intent("reminder.ambiguous",
                              {"options": tuple(e.to_dict() for e in found[:5]),
                               "query": asked}, stage="reminders")
            return Intent("reminder.unknown_app",
                          {"query": asked}, stage="reminders")
        # The words that did not go into the name are the thing to do,
        # not the program: "напомни когда открою студию проверить почту".
        text = (text + " " + leftover).strip() if leftover else text
        args["on"] = {"kind": "app.foreground", "app": entry.name,
                      "launch": entry.launch}
    else:
        if parsed.delay:
            args["seconds"] = parsed.delay
        if parsed.at:
            args["at"] = parsed.at

    if text:
        args["text"] = text
    return Intent("reminder.create", args, stage="reminders")


def _when_app(candidate, ctx):
    """
    Pull the program and the remainder out of "студию проверить почту".

    Speech gives no commas, and `normalize` removes them from typed text as
    well, so there is nothing to draw the boundary between the program's
    name and the thing to do — except knowledge of what is installed on the
    machine.

    **A word belongs to the name only if it changes the answer.** The index
    search is not strict, and "visual studio code слить" finds exactly what
    "visual studio code" finds: going from long to short and taking the
    first hit would absorb spare words into the name — which is what
    happened on the first attempt, and the thing to do lost its verb. So
    the **shortest** spelling that yields the same program is taken: words
    that changed nothing do not belong to the name.

    Returns (program | None, the remaining words, the candidates, the words
    actually in question). What is disputed is not settled silently — for
    the same reason as when learning: a reminder that did not fire shows
    nothing of itself, and the person finds out about the mistake when they
    were counting on the opposite.
    """
    from voice.textmatch import normalize

    words = candidate.split()
    unique = {}                      # size -> the single entry found
    plural = {}                      # size -> several candidates
    for size in range(1, len(words) + 1):
        found = apps_mod.find(" ".join(words[:size]), limit=5,
                              entries=ctx.apps)
        if len(found) == 1:
            unique[size] = found[0]
        elif found:
            plural[size] = found

    if not unique:
        # Not one unambiguous spelling. If several were found anywhere,
        # that is the dispute, and that is what to ask about: about the
        # words that produced the candidates, not about the whole phrase.
        if not plural:
            return None, "", [], candidate
        size = min(plural)
        return None, "", plural[size], " ".join(words[:size])

    longest = max(unique)
    entry = unique[longest]
    size = min(s for s, e in unique.items()
               if e.name == entry.name and e.launch == entry.launch)

    # A word that changed nothing but **stands in the name** belongs to
    # the name: "обс" already finds OBS Studio unambiguously, yet "студио"
    # in "обс студио" is the program, not the thing to do. The test is
    # against the found name itself, not against a guess at what the person
    # might have meant.
    known = set(normalize(entry.name).split())
    while size < len(words) and normalize(words[size]) in known:
        size += 1

    return entry, " ".join(words[size:]), [entry], " ".join(words[:size])


def _system(command, ctx):
    from voice import system_control

    action_id, needs_confirm = system_control.match_action(command)
    if not action_id:
        return None
    name = "system.confirm" if needs_confirm else "system.action"
    return Intent(name, {"action": action_id}, stage="system")


#: "Когда я говорю «код», открывай VS Code" — a rule stated aloud.
#:
#: The quotation marks are optional: speech recognition does not produce
#: them at all, and requiring them would make the rule available only from
#: the keyboard.
_RULE = re.compile(
    r"\b(?:когда|если)\s+я\s+(?:говорю|скажу)\s+"
    r"[«\"']?(?P<word>[^«»\"',]+?)[»\"']?\s*,?\s+"
    r"(?:открывай|запускай|открой|запусти|это)\s+(?P<app>.+)$",
    re.IGNORECASE)

#: "Нет, я имел в виду Chrome" — a correction following a launch.
#:
#: The speaker's gender does not matter and must not: "имела" is no
#: different from "имел".
_CORRECTION = re.compile(
    r"^(?:нет[,\s]+|не\s+т[оа]т[,\s]+|)?"
    r"я\s+имел[а]?\s+в\s+виду\s+(?P<app>.+)$",
    re.IGNORECASE)


def _todo(command, ctx):
    """
    Things to do (`4.0b-A13`).

    **The boundary is held by the vocabulary, not by the order.** Proved by
    breaking it: move this stage after the reminders and nothing changes —
    the reminder parsing takes none of these phrases. The word "напомни"
    belongs to reminders and is deliberately not given to the list as well:
    giving one word to two things makes a person guess which they will get.

    It stands early simply because the parsing is cheap and definite — but
    nothing depends on that, and writing here that something does would be
    untrue.

    Only a named thing can be closed: finding it among the list is the job
    of whoever holds the list, and the router hands on what was said.
    """
    parsed = todo_mod.parse(command)
    if parsed is None:
        return None
    what, rest = parsed

    if what == "list":
        return Intent("todo.list", stage="todo")
    if what == "add":
        return Intent("todo.add", {"text": rest}, stage="todo")

    # `done`: which one it is, the store knows, and the store answers if
    # there is none. The router decides nothing here — it has no list.
    found = list(ctx.todo_find(rest) or []) if ctx.todo_find else []
    if not found:
        return Intent("todo.not_found", {"query": rest}, stage="todo")
    if len(found) > 1:
        return Intent("todo.ambiguous",
                      {"options": [{"id": i["id"], "text": i["text"]}
                                   for i in found],
                       "query": rest}, stage="todo")
    return Intent("todo.done",
                  {"todo_id": found[0]["id"], "text": found[0]["text"]},
                  stage="todo")


#: "Why?" (`4.0b-B04`) — and only about **her own** doing.
#:
#: Deliberately narrow. "Почему трава зелёная" is a question about the
#: world, and answering it with "because you pressed a button" would be
#: worse than not understanding it at all. So: the bare word, or a question
#: addressed to her — «почему ты…», «зачем ты…» — or an explicit «объясни».
#: Everything else about the world goes on down the stages as before.
_WHY = re.compile(
    r"^(?:а\s+)?(?:"
    r"почему|зачем|отчего"
    r")\s*[?!.]*$"
    r"|^(?:а\s+)?(?:почему|зачем|отчего)\s+(?:ты|вы)\b"
    r"|^объясни(?:те)?(?:[,\s]+(?:почему|зачем))?\s*[?!.]*$",
    re.IGNORECASE)


def _why(command, ctx):
    """
    The person is asking about the last thing she did (`4.0b-B04`).

    The answer comes out of the call journal, and the router does not have
    one — nor should it: it decides what was meant, and what was actually
    done is known to whoever wrote it down.
    """
    if not _WHY.search(command.strip()):
        return None
    return Intent("why.last", stage="why")


def _teach(command, ctx):
    """
    The person stated a rule or corrected the previous launch
    (`4.0b-A04`).

    **Only what is stated aloud is learned.** There is no implicit learning
    from every conversation here and there will not be: the memory would
    fill with rubbish, the person would not be able to work out where the
    behaviour came from — and, worse, could not undo it, because they would
    not know what there was to undo.

    **What is disputed is not stored silently.** If the named program is
    itself ambiguous, or does not exist at all, an intent to ask is
    returned rather than one to write. A learned match lives a long time,
    and a mistake in it is the more unpleasant the later it is noticed.
    """
    rule = _RULE.search(command)
    if rule:
        return _teaching(rule.group("word"), rule.group("app"), ctx,
                         word_said=True)

    fix = _CORRECTION.search(command.strip())
    if fix and ctx.last_launch_query:
        return _teaching(ctx.last_launch_query, fix.group("app"), ctx,
                         word_said=False)
    return None


def _teaching(word, app, ctx, word_said):
    """A word and a program -> an intent to learn, to ask, or to refuse."""
    word = (word or "").strip(" \"'«».,")
    app = (app or "").strip(" \"'«».,")
    if not word or not app:
        return None

    found = apps_mod.find(app, limit=5, entries=ctx.apps)
    if not found:
        return Intent("alias.unknown", {"query": app, "word": word},
                      stage="teach")
    if len(found) > 1:
        # We always ask when there is more than one candidate — with no
        # thresholds and no guessing. A launch can be replayed by the next
        # phrase, while a learned match lives for years: the cost of asking
        # is lower than the cost of being wrong, and this is the case where
        # asking again is better.
        #
        # The options are dicts: this is the state of a question, and it is
        # obliged to survive being written to a file and travelling over
        # the protocol (4.0-B03).
        return Intent("alias.ambiguous",
                      {"options": tuple(e.to_dict() for e in found[:5]),
                       "query": app, "word": word}, stage="teach")

    entry = found[0]
    return Intent("alias.teach",
                  {"word": word, "app": entry.name,
                   "launch": entry.launch, "kind": entry.kind,
                   "said": word_said}, stage="teach")


def _launch(command, ctx):
    from voice import app_launcher

    decision = app_launcher.decide(command, apps=ctx.apps,
                                   aliases=ctx.aliases)
    if decision is None:
        return None
    if decision.status == "launch":
        # What was said travels with the decision. The launch tool has
        # long expected `query` — "what the user said, so as to remember
        # the choice" — but the router did not put it there, and the
        # parameter had been arriving empty all along. A correction needs
        # it too: "нет, я имел в виду Chrome" teaches the word, not the
        # program (`4.0b-A04`).
        return Intent("app.launch",
                      {"app": decision.entry.name, "query": decision.query},
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

    # With the microphone open on her own initiative we do not search:
    # noise and chance speech land here, and a browser must not be opened
    # on them.
    if ctx.web_fallback and not ctx.unbidden:
        return Intent("fallback.search", {"query": command}, stage="tail")

    return None
