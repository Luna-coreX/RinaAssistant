"""
Исполнение инструментов: единственный путь, по которому что-либо происходит.

Задача плана 4.0-C03. Реестр (core/toolbox.py) описывает, что Рина умеет;
здесь это выполняется — и только здесь.

Каждый вызов проходит четыре ворот в неизменном порядке:

    1. существует ли такой инструмент          -> tool.unknown
    2. годятся ли аргументы                    -> tool.invalid_arguments
    3. подтверждено ли опасное действие        -> confirmation.*
    4. и лишь потом — исполнение

Порядок не случаен. Проверка аргументов стоит раньше подтверждения, чтобы
человека не спрашивали про вызов, который всё равно не состоится. Проверка
подтверждения стоит раньше исполнения — иначе она бессмысленна.

**Почему реализации живут здесь, а не в исполнителе.** Критерий задачи —
«исполнитель не имеет ни одного пути в обход реестра». Пока побочный эффект
можно вызвать напрямую, запрет держится на дисциплине. Собранные в одном
модуле и достижимые только через `ToolRunner.call`, они держатся на
устройстве кода: чтобы обойти ворота, надо не забыть, а специально написать
обход.

Зависимости приходят снаружи одним объектом контекста — поэтому инструменты
проверяются с подставными хранилищами, не поднимая приложение.

Qt здесь нет: модуль лежит в ядре.
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
    """Всё, чем инструменты пользуются. Передаётся снаружи."""

    settings: Any = None
    reminders: Any = None
    commands: Any = None
    plugins: Any = None
    emit: Callable = None
    host: Any = None
    #: Запомнить выбор программы под сказанное слово.
    on_alias: Callable = None
    #: Кто трогает машину: громкость, медиа, питание, снимок.
    #: В 4.0 это оболочка (ADR 0009); в 3.1.0 было пусто и ядро делало само.
    system_out: Callable = None
    #: Кто запускает программы. Там же, где системный слой, и по той же
    #: причине: между намерением и созданием процесса должен стоять кто-то
    #: ещё, и этот кто-то — не тот, кто слушает микрофон.
    launch_app: Callable = None


class ToolResult:
    """Что вернул инструмент."""

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
# Реализации. Достижимы только через ToolRunner.call.
# ---------------------------------------------------------------------------
def _launch_app(ctx, args):
    from voice import app_index

    name = args["name"]
    entry = None
    for candidate in app_index.cached_index() or []:
        if candidate.name == name:
            entry = candidate
            break
    if entry is None:
        return ToolResult.failed(
            tr("Не нашла программу «{name}».", name=name), "app.not_found")

    # Запускает оболочка (ADR 0009): она же проверит канонический путь,
    # запрещённый каталог и подпись, и она же спросит человека, если файл
    # неподписанный (4.0-G10). Ядро сюда доходит, уже **решив**, что
    # запускать; «можно ли» — не его вопрос.
    launch = getattr(ctx, "launch_app", None)
    if launch is None:
        started, why = app_index.launch(entry), ""
    else:
        started, why = launch(entry.launch, entry.kind)

    if not started:
        # «Человек отказался» — не поломка: он ответил, и ответил «нет».
        # Код тот же, что у отказа в разрешении: для ядра это одно и то же
        # событие — человек сказал «нет», и повторять вопрос не надо.
        if "отказал" in why:
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
    from voice import app_index

    entries = app_index.cached_index() or []
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
    Сделать системное действие — руками оболочки (ADR 0009).

    Ядро решает **что** сделать и **как об этом сказать**; трогает машину
    оболочка. Слово остаётся здесь не из упрямства: «Прибавила громкость» —
    реплика Рины, и её язык задаёт ядро (`4.0-F08`); оболочка отвечает
    фактом «получилось».

    Своего пути в обход нет и в запасе: ядро, умеющее выключить компьютер
    само, тем и опасно, что умеет. Без оболочки действие не делается — и
    это верно, потому что без неё его и попросить некому.
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
    # Раньше снимок просили событием `window.action`: захват экрана был
    # операцией Qt и работал только из потока интерфейса. Теперь это
    # обычное системное действие — оболочка снимает экран сама и отвечает
    # путём к файлу, а событие «сделай что-нибудь с окном» осталось для
    # того, чем оно и было, — для окна.
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
        # Между шагами бывает пауза; вызывающий поток блокировать нельзя.
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
        # Плагин — чужой код. Его сбой не рвёт конвейер, но и не пропадает.
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
    """Единственный способ что-либо выполнить."""

    def __init__(self, context, registry=None, confirmations=None,
                 features=None, audit=None):
        self._ctx = context
        self._registry = registry or default_registry()
        self._confirmations = confirmations or ConfirmationLedger()
        self._features = features
        # Журнал вызовов (4.0-C06). Пишется здесь, потому что это
        # единственное место, где разом известны все шесть полей: время,
        # инструмент, аргументы, инициатор, разрешения и результат.
        self._audit = audit if audit is not None else AuditLog()

        missing = set(self._registry.names()) - set(IMPLEMENTATIONS)
        if missing:
            raise RuntimeError(
                f"объявлены, но не реализованы: {sorted(missing)}")

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
        Выдать подтверждение на конкретный вызов.

        Вызывается, когда человеку задают вопрос: идентификатор кладётся
        в заданный вопрос и предъявляется, когда человек согласится.
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
        Выполнить инструмент. Единственная дверь.

        Ошибки ворот возвращаются как ToolResult с кодом, а не бросаются:
        вызывающему всё равно нужно что-то сказать человеку, а исключение
        на каждый неверный аргумент превратило бы конвейер в лестницу
        try/except.
        """
        started = time.perf_counter()

        try:
            tool = self._registry.get(name)
        except UnknownTool as e:
            log.warning("Неизвестный инструмент: %s", name)
            # Записываем даже это: попытка вызвать несуществующее — след
            # чужой ошибки, и позже так будет видно промахи модели.
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
            result = IMPLEMENTATIONS[tool.name](self._ctx, checked)
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
        """Запись в журнал вызовов. Сбой журнала не мешает работе."""
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
        """Реестр словарями — для протокола и для оболочки."""
        return self._registry.describe()

    def permissions_of(self, name):
        return sorted(self._registry.get(name).permissions)

    def permission_titles(self, name):
        return [PERMISSIONS[p].title for p in self.permissions_of(name)]
