"""
The executor: intent -> tool call -> result.

Plan item 4.0-B04, reworked for 4.0-C03.

The executor used to produce the side effects itself: it called
`app_index.launch`, `system_control.run`, opened the browser. Now it **does
nothing itself** — it turns an intent into a tool call and hands it to
`ToolRunner`, which checks the arguments, the permissions and the
confirmation.

The split is for one reason: while a side effect is reachable from the
executor directly, any gates before it rest on discipline. C03's criterion —
"the executor has not one path of execution around the registry" — is
checked mechanically (tools/test_registry_only.py), and it can be checked
only if there is exactly one path.

What is left to the executor: knowing which tool answers each intent, and
turning the result into a line. The lines are here, because after 4.0-F08
the text of Rina's answers is assembled in the core, not in the shell.
"""

from core.i18n import t as tr
from core.intent import Result
from core.logging_setup import get_logger, safe


log = get_logger("executor")


class Executor:
    """Turns intents into tool calls."""

    def __init__(self, *, say, tools, emit=None):
        self._say = say
        self._tools = tools          # ToolRunner
        self._emit = emit

    @property
    def tools(self):
        return self._tools

    # ------------------------------------------------------------------
    def execute(self, intent, source="typed"):
        """An intent's namespace -> a method. Returns a Result."""
        handler = getattr(self, "_do_" + intent.name.replace(".", "_"), None)
        if handler is None:
            log.warning("Нечем исполнить намерение %s", intent.name)
            return Result.failure(error_code="internal")
        log.debug("Исполняю %s для %s", intent.name, safe(intent.text))
        return handler(intent, source)

    # ---------- programs ----------
    def _do_app_launch(self, intent, source):
        return self._run("launch_app", {
            "name": intent.arg("app"),
            "query": intent.arg("query") or "",
        }, source=source)

    def _do_app_ambiguous(self, intent, source):
        names = ", ".join(o.get("name", "") for o in
                          (intent.arg("options") or []))
        return self._ok(tr("Нашла несколько: {names}. Какое запустить?",
                           names=names))

    def _do_app_not_found(self, intent, source):
        from core.protocol import Events

        query = intent.arg("query")
        if query and self._emit:
            self._emit(Events.APP_NOT_FOUND, query=query)
        return self._fail(tr("Не нашла программу «{name}».", name=query),
                          "app.not_found")

    def _do_app_launch_failed(self, intent, source):
        return self._fail(
            tr("Не получилось запустить {app} — программу удалили "
               "или перенесли.", app=intent.arg("app")), "app.launch_failed")

    # ---------- the system ----------
    #: A 3.1.0 action -> (tool, arguments).
    _SYSTEM = {
        "volume_up": ("set_volume", {"action": "up"}),
        "volume_down": ("set_volume", {"action": "down"}),
        "volume_mute": ("set_volume", {"action": "mute"}),
        "media_next": ("media_control", {"action": "next"}),
        "media_prev": ("media_control", {"action": "previous"}),
        "media_play_pause": ("media_control", {"action": "play_pause"}),
        "lock": ("lock_screen", {}),
        "screenshot": ("take_screenshot", {}),
        "shutdown": ("power_action", {"action": "shutdown"}),
        "restart": ("power_action", {"action": "restart"}),
        "sleep": ("power_action", {"action": "sleep"}),
    }

    def _do_system_action(self, intent, source):
        mapping = self._SYSTEM.get(intent.arg("action"))
        if mapping is None:
            return Result.failure(error_code="internal")
        name, args = mapping
        return self._run(name, args,
                         confirmation_id=intent.arg("confirmation_id"),
                         source=source)

    def _do_system_confirm(self, intent, source):
        """
        Ask about a dangerous action.

        The confirmation is issued here and now and returned in the Result:
        the core puts its identifier into the question asked and will
        present it when the person agrees. That way consent is bound to a
        particular call rather than to the mere fact that a question was
        once asked.
        """
        from voice import system_control

        action = intent.arg("action")
        mapping = self._SYSTEM.get(action)
        if mapping is None:
            return Result.failure(error_code="internal")

        name, args = mapping
        question = system_control.confirm_question(action)
        confirmation = self._tools.request_confirmation(
            name, args, preview=question)
        result = self._ok(question)
        return result.with_data(confirmation_id=confirmation.id)

    # ---------- reminders ----------
    def _do_reminder_create(self, intent, source):
        args = {"kind": intent.arg("kind")}
        for key in ("seconds", "at", "text"):
            value = intent.arg(key)
            if value:
                args[key] = value
        return self._run("create_reminder", args, source=source)

    def _do_reminder_list(self, intent, source):
        return self._run("list_reminders", {}, source=source)

    def _do_reminder_cancel(self, intent, source):
        return self._run("cancel_reminder", {}, source=source)

    # ---------- user commands and plugins ----------
    def _do_user_command(self, intent, source):
        return self._run("run_user_command",
                         {"command_id": intent.arg("command_id")},
                         confirmation_id=intent.arg("confirmation_id"),
                         source=source)

    def dispatch_plugins(self, text, source="typed"):
        """Hand the phrase to the plugins. True means a plugin took it."""
        result = self._tools.call("dispatch_plugin_command", {"text": text},
                                  source=source)
        return bool(result.value)

    def run_user_command(self, command, source="shell"):
        """
        Perform a command by object — for the "Run" button in the list.

        The source is "shell" by default: a button was pressed, not a phrase
        said. In the call journal these are different initiators, and
        telling them apart matters.
        """
        return self._run("run_user_command",
                         {"command_id": command.get("id")}, source=source)

    # ---------- answers ----------
    def _do_calc(self, intent, source):
        return self._ok(tr("Получается {result}.",
                           result=intent.arg("result")))

    def _do_calc_zero_division(self, intent, source):
        return self._ok(tr("На ноль делить нельзя."))

    def _do_builtin_answer(self, intent, source):
        from voice.commands import ANSWERS

        make = ANSWERS.get(intent.arg("topic"))
        if make is None:
            return Result.failure(error_code="internal")
        return self._ok(make())

    def _do_websearch(self, intent, source):
        return self._run("web_search", {"query": intent.arg("query")},
                         source=source)

    def _do_cancelled(self, intent, source):
        return self._ok(tr("Хорошо, отменяю."))

    def _do_ask_wake(self, intent, source):
        return self._ok(tr("Да? Слушаю."))

    def _do_silence(self, intent, source):
        return Result.success()

    # ---------- the tail ----------
    def _do_llm_answer(self, intent, source):
        result = self._tools.call(
            "ask_model", {"question": intent.text}, source=source)
        if result.ok:
            return self._ok(result.message)
        return Result.failure(error_code=result.error_code)

    def _do_fallback_search(self, intent, source):
        from voice import websearch

        query = intent.arg("query") or intent.text
        result = self._tools.call("web_search", {"query": query},
                                  source=source)
        if not result.ok:
            return self._do_fallback_none(intent, source)
        # The wording of a fallback search differs from an explicit one: the
        # person did not ask to search, and it is more honest to say so.
        return self._ok(tr("Не нашла такой команды — поищу «{query}» "
                           "в интернете.", query=query))

    def _do_fallback_none(self, intent, source):
        return self._fail(tr("Извини, я не поняла команду."), "internal")

    # ---------- helpers ----------
    def _run(self, name, args, confirmation_id=None, *, source):
        """A tool call and the turning of the result into a line."""
        result = self._tools.call(name, args,
                                  confirmation_id=confirmation_id,
                                  source=source)
        if result.ok:
            return (self._ok(result.message) if result.message
                    else Result.success())
        return self._fail(result.message, result.error_code)

    def _ok(self, response):
        self._say(response)
        return Result.success(response)

    def _fail(self, response, error_code):
        self._say(response, sound="error")
        return Result.failure(response, error_code=error_code)
