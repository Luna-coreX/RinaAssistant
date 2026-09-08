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

    # `_teach` стоит перед `_launch` и после всего остального: выигрывать
    # ему надо только у запуска. «Когда я говорю "код", открывай VS Code»
    # содержит «открывай VS Code», и разбор запуска забрал бы фразу себе,
    # запустив редактор вместо того, чтобы выучить правило.
    #
    # А после `_answer_to_question` — потому что «нет» при заданном вопросе
    # остаётся отказом. Поправка приходит тогда, когда вопроса нет: Рина
    # уже запустила не то, и её поправляют вслед.
    for stage in (_answer_to_question, _reminder, _system, _teach, _launch,
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
    text = parsed.text

    # Напоминание, привязанное к программе (`4.0b-A03`).
    if parsed.when_app:
        entry, leftover, found, asked = _when_app(parsed.when_app, ctx)
        if entry is None:
            if len(found) > 1:
                return Intent("reminder.ambiguous",
                              {"options": tuple(e.to_dict() for e in found[:5]),
                               "query": asked}, stage="reminders")
            return Intent("reminder.unknown_app",
                          {"query": asked}, stage="reminders")
        # Слова, не вошедшие в название, — это дело, а не программа:
        # «напомни когда открою студию проверить почту».
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
    Из «студию проверить почту» вытащить программу и остаток.

    Речь не даёт запятых, а `normalize` убирает их и у набранного текста,
    поэтому границу между названием программы и делом провести нечем —
    кроме знания о том, что на машине установлено.

    **Слово входит в название, только если оно меняет ответ.** Поиск по
    индексу нестрогий, и «visual studio code слить» находит ровно то же,
    что «visual studio code»: идти от длинного к короткому и брать первое
    попавшееся значило бы вобрать в название лишние слова — так и вышло с
    первой попытки, дело потеряло свой глагол. Поэтому берётся **самое
    короткое** написание, дающее ту же программу: слова, ничего не
    изменившие, к названию не относятся.

    Возвращает (программа | None, остаток слов, кандидаты, слова, о
    которых речь). Спорное не
    решается молча — по той же причине, что и при обучении: несработавшее
    напоминание ничем себя не проявляет, и человек узнает об ошибке
    тогда, когда рассчитывал на обратное.
    """
    from voice.textmatch import normalize

    words = candidate.split()
    unique = {}                      # размер -> единственный найденный
    plural = {}                      # размер -> несколько кандидатов
    for size in range(1, len(words) + 1):
        found = apps_mod.find(" ".join(words[:size]), limit=5,
                              entries=ctx.apps)
        if len(found) == 1:
            unique[size] = found[0]
        elif found:
            plural[size] = found

    if not unique:
        # Ни одного однозначного написания. Если хоть где-то нашлось
        # несколько — это и есть спор, и спрашивать надо о нём: о тех
        # словах, которые кандидатов и дали, а не обо всей фразе.
        if not plural:
            return None, "", [], candidate
        size = min(plural)
        return None, "", plural[size], " ".join(words[:size])

    longest = max(unique)
    entry = unique[longest]
    size = min(s for s, e in unique.items()
               if e.name == entry.name and e.launch == entry.launch)

    # Слово, которое ничего не изменило, но **стоит в названии**, к
    # названию и относится: «обс» уже находит OBS Studio однозначно, но
    # «студио» из «обс студио» — это программа, а не дело. Проверка идёт
    # по самому найденному названию, а не по догадке о том, что человек
    # мог иметь в виду.
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


#: «Когда я говорю "код", открывай VS Code» — правило, названное вслух.
#:
#: Кавычки необязательны: распознавание речи их не выдаёт вовсе, и
#: требовать их значило бы сделать правило доступным только с клавиатуры.
_RULE = re.compile(
    r"\b(?:когда|если)\s+я\s+(?:говорю|скажу)\s+"
    r"[«\"']?(?P<word>[^«»\"',]+?)[»\"']?\s*,?\s+"
    r"(?:открывай|запускай|открой|запусти|это)\s+(?P<app>.+)$",
    re.IGNORECASE)

#: «Нет, я имел в виду Chrome» — поправка вслед запущенному.
#:
#: Род не важен и не должен быть: «имела» ничем не отличается от «имел».
_CORRECTION = re.compile(
    r"^(?:нет[,\s]+|не\s+т[оа]т[,\s]+|)?"
    r"я\s+имел[а]?\s+в\s+виду\s+(?P<app>.+)$",
    re.IGNORECASE)


def _teach(command, ctx):
    """
    Человек назвал правило или поправил прошлый запуск (`4.0b-A04`).

    **Учится только названное вслух.** Неявного обучения на всех разговорах
    здесь нет и не будет: память наполнилась бы мусором, а человек не смог
    бы понять, откуда взялось поведение — и, что хуже, не смог бы это
    отменить, потому что не знал бы, что отменять.

    **Спорное не сохраняется молча.** Если названная программа сама
    неоднозначна или её нет вовсе, возвращается намерение спросить, а не
    записать. Выученное соответствие живёт долго, и ошибка в нём тем
    неприятнее, чем позже её заметят.
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
    """Слово и программа -> намерение выучить, спросить или отказать."""
    word = (word or "").strip(" \"'«».,")
    app = (app or "").strip(" \"'«».,")
    if not word or not app:
        return None

    found = apps_mod.find(app, limit=5, entries=ctx.apps)
    if not found:
        return Intent("alias.unknown", {"query": app, "word": word},
                      stage="teach")
    if len(found) > 1:
        # Спрашиваем всегда, когда кандидатов больше одного, — без порогов
        # и без догадок. Запуск можно переиграть следующей фразой, а
        # выученное соответствие живёт годами: цена вопроса здесь ниже
        # цены ошибки, и это тот случай, когда лучше переспросить.
        #
        # Варианты — словарями: это состояние вопроса, и оно обязано
        # пережить запись в файл и дорогу по протоколу (4.0-B03).
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
        # Сказанное едет вместе с решением. Инструмент запуска давно ждёт
        # `query` — «что пользователь сказал, чтобы запомнить выбор», — а
        # роутер его не клал, и параметр всё это время приходил пустым.
        # Он же нужен поправке: «нет, я имел в виду Chrome» учит слову, а
        # не программе (`4.0b-A04`).
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

    # In "always listen" mode we do not search: noise and chance speech land
    # there, and a browser must not be opened on them.
    if ctx.web_fallback and ctx.source != "always":
        return Intent("fallback.search", {"query": command}, stage="tail")

    return None
