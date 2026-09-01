"""
Роутер: текст -> намерение. Чистая функция.

Задача плана 4.0-B02. До неё конвейер решал и исполнял одновременно: узнать,
что ядро поняло, можно было только по тому, что оно сделало. Из-за этого
разбор нельзя было ни проверить без побочных эффектов, ни отправить по
протоколу, ни поставить рядом языковую модель.

Правила, без которых смысла нет:

    * Роутер ничего не запускает, не говорит, не пишет в файлы и не ходит
      в сеть.
    * Роутер ничего не читает сам: всё, что ему нужно знать о мире, приходит
      в RouterContext. Поэтому его можно вызвать в тесте, не поднимая
      приложение, — и golden-набор проверяет именно его.
    * Возвращает Intent, а не текст ответа. Как это озвучить — дело
      исполнителя, и после 4.0-F08 текст вообще собирается в ядре отдельно.

Порядок шагов повторяет конвейер 3.1.0 буквально (docs/INVENTORY-3.1.0.md,
§1) — иначе изменится поведение, а рубеж 4.0-port это запрещает.

Чего роутер пока не решает: плагины и пользовательские команды. Плагин —
чужой код, и «взял бы он фразу» узнаётся только его запуском; пользовательские
команды сопоставляются чисто, но их исполнение всё ещё в ядре. Оба шага
переедут сюда вместе с 4.0-B03 и 4.0-B04. До тех пор ядро спрашивает их
раньше роутера, ровно как раньше.
"""

from dataclasses import dataclass, field

from core.intent import Intent


# Согласие и отказ на опасное действие. Живут здесь, а не в ядре: это часть
# разбора, и роутер обязан работать, не поднимая ядро.
# Требуем явного «да» — молчаливое согласие для выключения ПК недопустимо.
YES_WORDS = ("да", "давай", "подтверждаю", "точно", "выключай",
             "перезагружай", "усыпляй", "ага", "yes", "confirm")
NO_WORDS = ("нет", "отмена", "отмени", "не надо", "стоп", "no", "cancel")


@dataclass
class RouterContext:
    """
    Всё, что роутер знает о мире. Только чтение, никаких хранилищ.

    Собирается вызывающей стороной: ядром — из настроек и хранилищ,
    прогонщиком — вручную. Именно поэтому роутер тестируется без приложения.
    """

    #: Индекс установленных программ (список AppEntry).
    apps: list = field(default_factory=list)
    #: Выученные соответствия «как сказал» -> программа.
    aliases: dict = field(default_factory=dict)
    #: Незакрытый вопрос — словарь вида core.dialog.Question.to_dict().
    pending: dict = None
    #: Слова активации.
    wake_words: tuple = ("рина",)
    #: Требовать ли слово активации (режим «всегда слушать»).
    require_wake: bool = False
    #: Откуда пришла фраза: typed | voice | always.
    source: str = "typed"
    #: Сколько сейчас активных напоминаний — для list/cancel.
    reminders_active: int = 0
    #: Включён ли ответ языковой моделью.
    llm_enabled: bool = False
    #: Искать ли нераспознанное в интернете.
    web_fallback: bool = True
    #: Слова согласия и отказа для подтверждений.
    yes_words: tuple = YES_WORDS
    no_words: tuple = NO_WORDS


def route(text, ctx=None):
    """Текст -> Intent. Ничего не выполняет."""
    ctx = ctx or RouterContext()

    if not text:
        return Intent("silence", stage="empty", text="")

    command = _strip_wake(text, ctx)
    if command is None:
        return Intent("silence", stage="wake", text=text)
    if not command:
        # Слово активации прозвучало, команды нет. В режиме «всегда слушать»
        # не отвечаем: Рина услышала бы собственный ответ и зациклилась.
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
    """Команда без слова активации. None — активации не было."""
    if not ctx.require_wake:
        return text.strip()
    from voice.wake import strip_wake

    words = [w for w in (ctx.wake_words or ()) if w]
    if not words:
        return text.strip()
    return strip_wake(text, list(words))


def _answer_to_question(command, ctx):
    """Фраза — ответ на ранее заданный вопрос?"""
    pending = ctx.pending
    if not pending:
        return None

    kind = pending.get("kind")
    if kind in ("confirm_action", "confirm_command"):
        from voice.textmatch import normalize

        words = normalize(command).split()
        # Отказ проверяется раньше согласия — так ведёт себя 3.1.0, и
        # «нет, давай» читается как отказ (см. инвентарь, §2).
        if any(w in words for w in ctx.no_words):
            return Intent("cancelled", {"was": kind,
                                        "action": pending.get("action", "")},
                          stage="pending")
        if any(w in words for w in ctx.yes_words):
            # Подтверждение из вопроса едет вместе с намерением: без него
            # опасное действие отклонит реестр (4.0-C05).
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
        return None            # невнятный ответ — вопрос снимется, см. ядро

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
        # Варианты — словарями, а не объектами: это состояние вопроса, и оно
        # обязано переживать запись в файл и дорогу по протоколу (4.0-B03).
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
    """Хвост конвейера: модель, затем поиск, затем отказ."""
    if ctx.llm_enabled:
        # Роутер не спрашивает модель — это сеть и секунды. Он лишь называет
        # намерение; спрашивает исполнитель.
        return Intent("llm.answer", stage="tail", confidence=0.5)

    # В режиме «всегда слушать» не ищем: туда попадают шум и случайная речь,
    # открывать по ним браузер нельзя.
    if ctx.web_fallback and ctx.source != "always":
        return Intent("fallback.search", {"query": command}, stage="tail")

    return None
