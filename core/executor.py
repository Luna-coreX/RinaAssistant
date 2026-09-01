"""
Исполнитель: намерение -> вызов инструмента -> результат.

Задача плана 4.0-B04, переработан под 4.0-C03.

Раньше исполнитель сам делал побочные эффекты: звал `app_index.launch`,
`system_control.run`, открывал браузер. Теперь он **ничего не делает сам** —
он переводит намерение в вызов инструмента и отдаёт его `ToolRunner`, который
проверяет аргументы, разрешения и подтверждение.

Разделение по одной причине: пока побочный эффект достижим из исполнителя
напрямую, любые ворота перед ним держатся на дисциплине. Критерий C03 —
«исполнитель не имеет ни одного пути исполнения в обход реестра» — проверяется
механически (tools/test_registry_only.py), и проверять его можно только если
путь ровно один.

Что осталось исполнителю: знать, каким инструментом отвечает каждое намерение,
и превратить результат в реплику. Реплики — здесь, потому что после 4.0-F08
текст ответов Рины собирается в ядре, а не в оболочке.
"""

from core.i18n import t as tr
from core.intent import Result
from core.logging_setup import get_logger, safe


log = get_logger("executor")


class Executor:
    """Переводит намерения в вызовы инструментов."""

    def __init__(self, *, say, tools, emit=None):
        self._say = say
        self._tools = tools          # ToolRunner
        self._emit = emit

    @property
    def tools(self):
        return self._tools

    # ------------------------------------------------------------------
    def execute(self, intent, source="typed"):
        """Namespace намерения -> метод. Возвращает Result."""
        handler = getattr(self, "_do_" + intent.name.replace(".", "_"), None)
        if handler is None:
            log.warning("Нечем исполнить намерение %s", intent.name)
            return Result.failure(error_code="internal")
        log.debug("Исполняю %s для %s", intent.name, safe(intent.text))
        return handler(intent, source)

    # ---------- программы ----------
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

    # ---------- система ----------
    #: Действие 3.1.0 -> (инструмент, аргументы).
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
        Задать вопрос об опасном действии.

        Подтверждение выдаётся здесь же и возвращается в Result: ядро кладёт
        его идентификатор в заданный вопрос и предъявит, когда человек
        согласится. Так согласие оказывается привязано к конкретному вызову,
        а не к самому факту, что вопрос когда-то задавали.
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

    # ---------- напоминания ----------
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

    # ---------- пользовательские команды и плагины ----------
    def _do_user_command(self, intent, source):
        return self._run("run_user_command",
                         {"command_id": intent.arg("command_id")},
                         confirmation_id=intent.arg("confirmation_id"),
                         source=source)

    def dispatch_plugins(self, text, source="typed"):
        """Отдать фразу плагинам. True — плагин её взял."""
        result = self._tools.call("dispatch_plugin_command", {"text": text},
                                  source=source)
        return bool(result.value)

    def run_user_command(self, command, source="shell"):
        """
        Выполнить команду по объекту — для кнопки «Выполнить» в списке.

        Источник по умолчанию «shell»: нажали кнопку, а не сказали фразу.
        В журнале вызовов это разные инициаторы, и различать их важно.
        """
        return self._run("run_user_command",
                         {"command_id": command.get("id")}, source=source)

    # ---------- ответы ----------
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

    # ---------- хвост ----------
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
        # Формулировка запасного поиска отличается от явного: человек не
        # просил искать, и об этом честнее сказать.
        return self._ok(tr("Не нашла такой команды — поищу «{query}» "
                           "в интернете.", query=query))

    def _do_fallback_none(self, intent, source):
        return self._fail(tr("Извини, я не поняла команду."), "internal")

    # ---------- вспомогательное ----------
    def _run(self, name, args, confirmation_id=None, *, source):
        """Вызов инструмента и превращение результата в реплику."""
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
