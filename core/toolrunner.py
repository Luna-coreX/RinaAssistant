"""
Running tools: the only path by which anything happens at all.

Plan item 4.0-C03. The registry (core/toolbox.py) describes what Rina can
do; here it is performed — and only here.

Every call passes four gates in an unchanging order:

    1. does such a tool exist                 -> tool.unknown
    2. are the arguments suitable             -> tool.invalid_arguments
    3. is the dangerous action confirmed      -> confirmation.*
    4. and only then — execution

The order is not accidental. The argument check comes before confirmation so
that a person is not asked about a call that will not take place anyway. The
confirmation check comes before execution — otherwise it is meaningless.

**Why the implementations live here rather than in the executor.** The
task's criterion is "the executor has not one path around the registry".
While a side effect can be called directly, the prohibition rests on
discipline. Gathered in one module and reachable only through
`ToolRunner.call`, they rest on the way the code is built: to get around the
gates one must not merely forget but deliberately write a way around.

The dependencies come from outside as one context object — which is why the
tools are checked with stand-in stores, without raising the application.

There is no Qt here: the module lies in the core.
"""

import time
from dataclasses import dataclass
from typing import Any, Callable

from core.audit import AuditLog
from core.confirmations import ConfirmationError, ConfirmationLedger
from core.i18n import t as tr
from core.logging_setup import get_logger, safe, security_log
from core.permissions import PERMISSIONS
from core.tools import ToolError, UnknownTool
from core.toolbox import default_registry


log = get_logger("tools")


@dataclass
class ToolContext:
    """Everything the tools use. Passed in from outside."""

    settings: Any = None
    reminders: Any = None
    commands: Any = None
    plugins: Any = None
    emit: Callable = None
    host: Any = None
    #: Remember the choice of program under the word that was said.
    on_alias: Callable = None
    #: Who touches the machine: volume, media, power, a screenshot.
    #: In 4.0 that is the shell (ADR 0009); in 3.1.0 it was empty and the
    #: core did it itself.
    system_out: Callable = None
    #: Who launches programs. The same place as the system layer, and for
    #: the same reason: somebody else must stand between an intent and the
    #: creation of a process, and that somebody is not whoever listens to the
    #: microphone.
    launch_app: Callable = None
    #: Where to get the program index from.
    #:
    #: It appeared because without it the tools searched a **different** list
    #: from the router's: the router asked the shell (4.0-G06), and they
    #: asked the scanner's cache, which in 4.0 nobody fills. Rina offered a
    #: choice of three and then answered that she had found none.
    apps: Callable = None


class ToolResult:
    """What a tool returned."""

    __slots__ = ("ok", "value", "message", "error_code")

    def __init__(self, ok=True, value=None, message="", error_code=""):
        self.ok = ok
        self.value = value
        self.message = message
        self.error_code = error_code

    @classmethod
    def done(cls, message="", value=None):
        return cls(True, value, message)

    @classmethod
    def failed(cls, message, error_code="internal"):
        return cls(False, None, message, error_code)

    def __repr__(self):
        state = "ok" if self.ok else f"ошибка {self.error_code}"
        return f"<ToolResult {state}: {self.message!r}>"


# ---------------------------------------------------------------------------
# The implementations. Reachable only through ToolRunner.call.
# ---------------------------------------------------------------------------
def _index(ctx):
    """
    The program index — the same one the router sees.

    Exactly one source: two lists answering one question will one day answer
    differently, and that has already happened.
    """
    source = getattr(ctx, "apps", None)
    if source is not None:
        return source() or []

    from voice import app_index

    return app_index.cached_index() or []


def _launch_app(ctx, args):
    from voice import app_index

    name = args["name"]
    entry = None
    for candidate in _index(ctx):
        if candidate.name == name:
            entry = candidate
            break
    if entry is None:
        return ToolResult.failed(
            tr("Не нашла программу «{name}».", name=name), "app.not_found")

    # The shell launches (ADR 0009): it is also what checks the canonical
    # path, the forbidden directory and the signature, and it is what asks
    # the person if the file is unsigned (4.0-G10). The core reaches this
    # point having already **decided** what to launch; "may I" is not its
    # question.
    launch = getattr(ctx, "launch_app", None)
    if launch is None:
        started, why = app_index.launch(entry), ""
    else:
        started, why = launch(entry.launch, entry.kind)

    if not started:
        # "The person refused" is not a fault: they answered, and the
        # answer was no. The error code is the same as for a denied
        # permission — for the core it is one and the same event, and the
        # question should not be repeated.
        #
        # The shell replies with a code, not a phrase: matching on a
        # substring of prose broke the moment the shell was translated.
        if why == "refused":
            return ToolResult.failed(tr("Не стала запускать."),
                                     "permission.denied")
        return ToolResult.failed(
            tr("Не получилось запустить {app} — программу удалили "
               "или перенесли.", app=entry.name), "app.launch_failed")

    query = args.get("query")
    if query and ctx.on_alias:
        ctx.on_alias(query, entry)
    return ToolResult.done(tr("Запускаю {app}.", app=entry.name), entry.name)


def _list_apps(ctx, args):
    entries = _index(ctx)
    query = (args.get("query") or "").strip().lower()
    if query:
        entries = [e for e in entries if query in e.name.lower()]
    entries = entries[:args.get("limit", 20)]
    return ToolResult.done(value=[e.to_dict() for e in entries])


_VOLUME = {"up": "volume_up", "down": "volume_down", "mute": "volume_mute"}
_MEDIA = {"next": "media_next", "previous": "media_prev",
          "play_pause": "media_play_pause"}


def _run_system(ctx, action_id):
    """
    Perform a system action — by the shell's hands (ADR 0009).

    The core decides **what** to do and **how to say so about it**; the
    shell touches the machine. The word stays here not out of stubbornness:
    "Volume turned up" is Rina's line, and its language is set by the core
    (`4.0-F08`); the shell answers with the fact "it worked".

    There is no way around it, not even in reserve: a core that can shut the
    computer down itself is dangerous precisely because it can. Without the
    shell the action is not performed — and that is right, because without
    it there is nobody to ask for it either.
    """
    from voice import system_control

    do = getattr(ctx, "system_out", None)
    if do is None:
        return ToolResult.failed(
            tr("Системные действия делает оболочка, а связи с ней нет."),
            "internal")

    ok, detail = do(action_id)
    if not ok:
        return ToolResult.failed(tr("Не получилось выполнить действие."),
                                 "internal")
    if action_id == "screenshot" and detail:
        return ToolResult.done(tr("Снимок сохранён: ") + detail)
    return ToolResult.done(tr(system_control.DONE_MESSAGES.get(action_id)
                              or "Готово."))


def _set_volume(ctx, args):
    return _run_system(ctx, _VOLUME[args["action"]])


def _media_control(ctx, args):
    return _run_system(ctx, _MEDIA[args["action"]])


def _lock_screen(ctx, args):
    return _run_system(ctx, "lock")


def _power_action(ctx, args):
    return _run_system(ctx, args["action"])


def _take_screenshot(ctx, args):
    # A screenshot used to be asked for with the `window.action` event:
    # capturing the screen was a Qt operation and worked only from the
    # interface thread. Now it is an ordinary system action — the shell
    # takes the screenshot itself and answers with a path to the file — and
    # the "do something with the window" event stayed for what it always
    # was: for the window.
    return _run_system(ctx, "screenshot")


def _create_reminder(ctx, args):
    import time

    from voice import reminders

    seconds = args.get("seconds")
    at = args.get("at")
    text = args.get("text") or ""
    fire_at = at if at else time.time() + (seconds or 0)
    ctx.reminders.add(args["kind"], fire_at, text)

    if seconds:
        left = reminders.humanize_left(seconds)
        if text:
            return ToolResult.done(
                tr("Напомню через {left}: {text}.", left=left, text=text))
        return ToolResult.done(tr("Засекла {left}.", left=left))

    when = reminders.when_text(fire_at)
    if text:
        return ToolResult.done(
            tr("Напомню в {time}: {text}.", time=when, text=text))
    return ToolResult.done(tr("Разбужу в {time}.", time=when))


def _list_reminders(ctx, args):
    from voice import reminders

    items = sorted(ctx.reminders.active(), key=lambda r: r.get("fire_at", 0))
    if not items:
        return ToolResult.done(tr("Ничего не запланировано."), [])
    message = tr("Запланировано: ") + "; ".join(
        reminders.describe(i) for i in items[:5])
    return ToolResult.done(message, items)


def _cancel_reminder(ctx, args):
    target = args.get("id")
    if target:
        removed = 1 if ctx.reminders.remove(target) else 0
    else:
        removed = ctx.reminders.clear_active()
    if not removed:
        return ToolResult.done(tr("Нечего отменять."), 0)
    return ToolResult.done(tr("Отменила: {count}.", count=removed), removed)


def _run_user_command(ctx, args):
    import threading

    from voice.user_commands import execute

    command_id = args["command_id"]
    command = None
    for candidate in ctx.commands.all():
        if candidate.get("id") == command_id:
            command = candidate
            break
    if command is None:
        return ToolResult.failed(tr("Не получилось выполнить команду."),
                                 "internal")

    ctx.commands.bump_stat(command_id)
    if command.get("type") == "sequence":
        # There is sometimes a pause between steps; the calling thread must not be blocked.
        def worker():
            execute(command, ctx.host, ctx.emit)

        threading.Thread(target=worker, daemon=True).start()
        return ToolResult.done(tr("Выполняю последовательность."))

    ok, response = execute(command, ctx.host, ctx.emit)
    return (ToolResult.done(response) if ok
            else ToolResult.failed(response, "internal"))


def _dispatch_plugin_command(ctx, args):
    if ctx.plugins is None:
        return ToolResult.done(value=False)
    try:
        taken = bool(ctx.plugins.dispatch_command(args["text"]))
    except Exception:
        # A plugin is somebody else's code. Its failure does not tear the pipeline, nor does it vanish.
        log.exception("Сбой плагина при разборе команды")
        return ToolResult.done(value=False)
    return ToolResult.done(value=taken)


def _calculate(ctx, args):
    from voice import calculator

    found = calculator.classify(args["expression"])
    if not found:
        return ToolResult.failed(tr("Извини, я не поняла команду."),
                                 "tool.invalid_arguments")
    name, result = found
    if name == "calc.zero_division":
        return ToolResult.done(tr("На ноль делить нельзя."))
    return ToolResult.done(
        tr("Получается {result}.", result=result["result"]),
        result["result"])


def _web_search(ctx, args):
    from voice import websearch

    engine = args.get("engine") or ctx.settings.get(
        "search_engine", websearch.DEFAULT_ENGINE)
    query = args["query"]
    if websearch.open_search(query, engine):
        return ToolResult.done(
            tr("Ищу «{query}» в {engine}.", query=query,
               engine=websearch.engine_label(engine)))
    return ToolResult.failed(tr("Не удалось открыть браузер для поиска."),
                             "internal")


def _ask_model(ctx, args):
    from core import llm

    try:
        answer = llm.ask(args["question"], args.get("context"))
    except llm.LLMError as e:
        return ToolResult.failed(str(e), "llm.unavailable")
    except Exception as e:
        return ToolResult.failed(str(e), "llm.unavailable")
    return ToolResult.done(answer, answer)


IMPLEMENTATIONS = {
    "launch_app": _launch_app,
    "list_apps": _list_apps,
    "set_volume": _set_volume,
    "media_control": _media_control,
    "lock_screen": _lock_screen,
    "power_action": _power_action,
    "take_screenshot": _take_screenshot,
    "create_reminder": _create_reminder,
    "list_reminders": _list_reminders,
    "cancel_reminder": _cancel_reminder,
    "run_user_command": _run_user_command,
    "dispatch_plugin_command": _dispatch_plugin_command,
    "calculate": _calculate,
    "web_search": _web_search,
    "ask_model": _ask_model,
}


# ---------------------------------------------------------------------------
class ToolRunner:
    """The only way to perform anything."""

    def __init__(self, context, registry=None, confirmations=None,
                 features=None, audit=None):
        self._ctx = context
        self._registry = registry or default_registry()
        self._confirmations = confirmations or ConfirmationLedger()
        self._features = features
        # The call journal (4.0-C06). Written here, because this is the only
        # place where all six fields are known at once: the time, the tool,
        # the arguments, the initiator, the permissions and the result.
        self._audit = audit if audit is not None else AuditLog()

        #: The implementations of plugins' tools (`4.0-H03`). On the
        #: instance rather than in a module dictionary: two cores in one
        #: process must not share other plugins' tools (`4.0-B05`), and a
        #: plugin that is removed is obliged to take its tools with it.
        self._added = {}

        missing = set(self._registry.names()) - set(IMPLEMENTATIONS)
        if missing:
            raise RuntimeError(
                f"объявлены, но не реализованы: {sorted(missing)}")

    def add_tool(self, tool, run):
        """
        Add a plugin's tool to the registry.

        A plugin declares rather than does (ADR 0010): a declared tool goes
        the same path as a built-in one — the permission check, the
        confirmation of the irreversible, the journal entry saying who
        started this. A plugin calling `subprocess` itself would get around
        all of that, and then a person's consent to "launching programs"
        would be self-deception.
        """
        self._registry.register(tool)
        self._added[tool.name] = run
        return tool

    def drop_tools(self, prefix):
        """Remove the tools of a switched-off plugin."""
        gone = [name for name in self._added if name.startswith(prefix)]
        for name in gone:
            self._added.pop(name, None)
            self._registry.forget(name)
        return gone

    @property
    def registry(self):
        return self._registry

    @property
    def confirmations(self):
        return self._confirmations

    @property
    def audit(self):
        return self._audit

    # ------------------------------------------------------------------
    def needs_confirmation(self, name):
        return self._registry.get(name).confirm_required

    def request_confirmation(self, name, args=None, preview="", ttl=None):
        """
        Issue a confirmation for a particular call.

        Called when a person is asked a question: the identifier is put into
        the question asked and presented when the person agrees.
        """
        tool = self._registry.get(name)
        checked = self._registry.validate(name, args)
        confirmation = self._confirmations.issue(
            tool.name, checked, ttl=ttl, preview=preview)
        security_log().info(
            "Запрошено подтверждение: %s %s", tool.name, checked)
        return confirmation

    # ------------------------------------------------------------------
    def call(self, name, args=None, confirmation_id=None,
             source="typed", trace_id=""):
        """
        Perform a tool. The only door.

        Gate errors are returned as a ToolResult with a code rather than
        raised: the caller has to say something to the person anyway, and an
        exception per wrong argument would turn the pipeline into a
        staircase of try/except.
        """
        started = time.perf_counter()

        try:
            tool = self._registry.get(name)
        except UnknownTool as e:
            log.warning("Неизвестный инструмент: %s", name)
            # We record even this: an attempt to call something that does
            # not exist is a trace of somebody's mistake, and later it will
            # show the model's misses.
            self._write(name, args, source, (), False, e.code,
                        started, confirmation_id, trace_id)
            return ToolResult.failed(e.message, e.code)

        try:
            checked = self._registry.validate(name, args)
        except ToolError as e:
            log.warning("Аргументы отклонены: %s", e.message)
            self._write(tool, args, source, tool.permissions, False, e.code,
                        started, confirmation_id, trace_id)
            return ToolResult.failed(e.message, e.code)

        if tool.confirm_required:
            try:
                confirmation = self._confirmations.redeem(
                    confirmation_id, tool.name, checked)
            except ConfirmationError as e:
                security_log().warning(
                    "Опасное действие отклонено без подтверждения: %s %s (%s)",
                    tool.name, checked, e.code)
                self._write(tool, checked, source, tool.permissions, False,
                            e.code, started, confirmation_id, trace_id)
                return ToolResult.failed(
                    tr("Это действие нужно подтвердить."), e.code)
            security_log().warning(
                "Опасное действие подтверждено и выполняется: %s %s "
                "(подтверждение %s)", tool.name, checked, confirmation.id)

        log.debug("Вызов %s(%s) из %s", tool.name, checked, source)
        try:
            run = self._added.get(tool.name) or IMPLEMENTATIONS[tool.name]
            result = run(self._ctx, checked)
        except Exception as e:
            log.exception("Инструмент %s упал", tool.name)
            self._write(tool, checked, source, tool.permissions, False,
                        "internal", started, confirmation_id, trace_id)
            return ToolResult.failed(str(e), "internal")

        self._write(tool, checked, source, tool.permissions, result.ok,
                    result.error_code, started, confirmation_id, trace_id)
        return result

    def _write(self, tool, args, source, permissions, ok, error_code,
               started, confirmation_id, trace_id):
        """An entry in the call journal. A journal failure does not get in the way of work."""
        if self._audit is None:
            return
        try:
            from core.logging_setup import texts_allowed

            self._audit.record(
                tool=tool, args=args, source=source, permissions=permissions,
                ok=ok, error_code=error_code,
                duration_ms=int((time.perf_counter() - started) * 1000),
                confirmation_id=confirmation_id or "", trace_id=trace_id or "",
                verbatim=texts_allowed())
        except Exception:
            log.exception("Не удалось записать вызов в журнал")

    # ------------------------------------------------------------------
    def describe(self):
        """The registry as dicts — for the protocol and for the shell."""
        return self._registry.describe()

    def permissions_of(self, name):
        return sorted(self._registry.get(name).permissions)

    def permission_titles(self, name):
        return [PERMISSIONS[p].title for p in self.permissions_of(name)]
