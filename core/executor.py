"""
Исполнитель: намерение -> действие -> результат.

Задача плана 4.0-B04. Единственное место, где происходят побочные эффекты:
запускаются программы, меняется громкость, пишутся напоминания, открывается
браузер, спрашивается языковая модель.

Зачем сводить в одну точку. Пока побочные эффекты разбросаны по конвейеру,
нельзя ни перечислить их, ни поставить перед ними проверку разрешений, ни
показать предпросмотр опасного действия. Всё это — 4.0-C03, C04 и C05, и все
они опираются на то, что путь исполнения ровно один.

Что исполнитель НЕ делает: не разбирает текст (это роутер) и не решает, задан
ли вопрос (это core/dialog.py). Он получает готовое намерение.

Зависимости приходят снаружи — хранилища, озвучка, шина событий. Поэтому
исполнителя можно собрать в тесте с подставными хранилищами и проверить, что
он сделал, не поднимая приложение.
"""

import threading
import time

from core.i18n import t as tr
from core.intent import Result
from core.logging_setup import get_logger, safe


log = get_logger("executor")


class Executor:
    """Выполняет намерения. Всё, что меняет мир, происходит здесь."""

    def __init__(self, *, say, emit, settings, reminders_store,
                 command_store, host=None, on_alias=None):
        self._say = say
        self._emit = emit
        self._settings = settings
        self._reminders = reminders_store
        self._commands = command_store
        self._host = host
        self._on_alias = on_alias          # запомнить выбор программы

    # ------------------------------------------------------------------
    def execute(self, intent, source="typed"):
        """Namespace намерения -> метод. Возвращает Result."""
        handler = getattr(self, "_do_" + intent.name.replace(".", "_"), None)
        if handler is None:
            log.warning("Нечем исполнить намерение %s", intent.name)
            return Result.failure(error_code="internal")
        log.debug("Исполняю %s для %s", intent.name, safe(intent.text))
        return handler(intent, source)

    # ---------- запуск программ ----------
    def _do_app_launch(self, intent, source):
        from voice import app_index

        name = intent.arg("app")
        entry = self._find_entry(name)
        if entry is None:
            return self._fail(tr("Не нашла программу «{name}».", name=name),
                              "app.not_found")
        if not app_index.launch(entry):
            return self._fail(
                tr("Не получилось запустить {app} — программу удалили "
                   "или перенесли.", app=entry.name), "app.launch_failed")

        # Выбор из нескольких запоминается: в следующий раз без вопроса.
        query = intent.arg("query")
        if query and self._on_alias:
            self._on_alias(query, entry)
        return self._ok(tr("Запускаю {app}.", app=entry.name))

    def _do_app_ambiguous(self, intent, source):
        names = ", ".join(o.get("name", "") for o in
                          (intent.arg("options") or []))
        return self._ok(tr("Нашла несколько: {names}. Какое запустить?",
                           names=names))

    def _do_app_not_found(self, intent, source):
        from core.protocol import Events

        query = intent.arg("query")
        result = self._fail(tr("Не нашла программу «{name}».", name=query),
                            "app.not_found")
        if query:
            self._emit(Events.APP_NOT_FOUND, query=query)
        return result

    def _do_app_launch_failed(self, intent, source):
        return self._fail(
            tr("Не получилось запустить {app} — программу удалили "
               "или перенесли.", app=intent.arg("app")), "app.launch_failed")

    def _find_entry(self, name):
        from voice import app_index

        for entry in app_index.cached_index() or []:
            if entry.name == name:
                return entry
        return None

    # ---------- напоминания ----------
    def _do_reminder_create(self, intent, source):
        from voice import reminders

        seconds = intent.arg("seconds")
        at = intent.arg("at")
        text = intent.arg("text") or ""
        fire_at = at if at else time.time() + (seconds or 0)
        self._reminders.add(intent.arg("kind"), fire_at, text)

        if seconds:
            left = reminders.humanize_left(seconds)
            if text:
                return self._ok(tr("Напомню через {left}: {text}.",
                                   left=left, text=text))
            return self._ok(tr("Засекла {left}.", left=left))

        when = reminders.when_text(fire_at)
        if text:
            return self._ok(tr("Напомню в {time}: {text}.", time=when,
                               text=text))
        return self._ok(tr("Разбужу в {time}.", time=when))

    def _do_reminder_list(self, intent, source):
        from voice import reminders

        items = sorted(self._reminders.active(),
                       key=lambda r: r.get("fire_at", 0))
        if not items:
            return self._ok(tr("Ничего не запланировано."))
        return self._ok(tr("Запланировано: ") + "; ".join(
            reminders.describe(i) for i in items[:5]))

    def _do_reminder_cancel(self, intent, source):
        removed = self._reminders.clear_active()
        if not removed:
            return self._ok(tr("Нечего отменять."))
        return self._ok(tr("Отменила: {count}.", count=removed))

    # ---------- система ----------
    def _do_system_action(self, intent, source):
        from core.protocol import Events
        from voice import system_control

        action = intent.arg("action")
        # Снимок экрана делает оболочка: сообщаем ей через СВОЮ шину.
        if action in system_control.WINDOW_ACTIONS:
            self._emit(Events.WINDOW_ACTION, action=action)
            return self._ok(system_control.run(action))

        message = system_control.run(action)
        if message is None:
            return Result.failure(error_code="internal")
        failed = message == tr("Не получилось выполнить действие.")
        return (self._fail(message, "internal") if failed
                else self._ok(message))

    def _do_system_confirm(self, intent, source):
        from voice import system_control

        return self._ok(system_control.confirm_question(intent.arg("action")))

    def _do_command_confirm(self, intent, source):
        return self._ok(intent.arg("question") or tr("Точно выполнить?"))

    # ---------- пользовательские команды ----------
    def _do_user_command(self, intent, source):
        command_id = intent.arg("command_id")
        for command in self._commands.all():
            if command.get("id") == command_id:
                return self.run_user_command(command)
        return Result.failure(error_code="internal")

    def run_user_command(self, command):
        """
        Выполняет пользовательскую команду.

        Последовательности уходят в фоновый поток: между шагами бывает пауза,
        а вызывающий поток блокировать нельзя.
        """
        from voice.user_commands import execute

        self._commands.bump_stat(command.get("id"))
        if command.get("type") == "sequence":
            def worker():
                _ok, response = execute(command, self._host,
                                        self._emit)
                self._say(response)
            threading.Thread(target=worker, daemon=True).start()
            return Result.success()

        ok, response = execute(command, self._host, self._emit)
        self._say(response, sound="response" if ok else "error")
        return Result(ok=ok, response=response)

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
        from voice import websearch

        engine = self._settings.get("search_engine", websearch.DEFAULT_ENGINE)
        query = intent.arg("query")
        if websearch.open_search(query, engine):
            return self._ok(tr("Ищу «{query}» в {engine}.", query=query,
                               engine=websearch.engine_label(engine)))
        return self._fail(tr("Не удалось открыть браузер для поиска."),
                          "internal")

    def _do_cancelled(self, intent, source):
        return self._ok(tr("Хорошо, отменяю."))

    def _do_ask_wake(self, intent, source):
        return self._ok(tr("Да? Слушаю."))

    def _do_silence(self, intent, source):
        return Result.success()

    # ---------- хвост ----------
    def _do_fallback_search(self, intent, source):
        from voice import websearch

        engine = self._settings.get("search_engine", websearch.DEFAULT_ENGINE)
        found = websearch.fallback_search(intent.arg("query"), engine)
        if found:
            return self._ok(found)
        return self._do_fallback_none(intent, source)

    def _do_fallback_none(self, intent, source):
        return self._fail(tr("Извини, я не поняла команду."), "internal")

    # ---------- вспомогательное ----------
    def _ok(self, response):
        self._say(response)
        return Result.success(response)

    def _fail(self, response, error_code):
        self._say(response, sound="error")
        return Result.failure(response, error_code=error_code)
