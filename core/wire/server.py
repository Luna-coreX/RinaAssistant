"""
Серверная сторона протокола: ядро отвечает по проводу.

Задача плана `4.0-E02`; спецификация — вся, и это её первый настоящий
потребитель.

До сих пор пакет `core/wire` умел собирать и разбирать сообщения, но ни с
чем не был связан: conformance-набор говорил с эталонным ядром, написанным
тут же рядом. Здесь провод соединяется с настоящим `core/engine.py`.

**Ядро решает, оболочка показывает.** Ответ на команду — не текст ответа, а
«принято в обработку»: сам ответ придёт событием `assistant.response`, когда
он появится. Так и работает 3.1.0, где команда может думать секундами и
успеть сказать несколько вещей; выдать её результат ответом на запрос значило
бы держать запрос открытым всё это время и потерять всё, кроме последнего.

**События ядра переливаются в события протокола один к одному.** Каталог
`core/wire/events.py` для того и сверялся с `core/protocol.py`: перекладка не
переименовывает и не додумывает, иначе к двум спискам добавился бы третий —
таблица соответствия, которую тоже пришлось бы сверять.

**Обрыв канала — это смерть оболочки, и ядро завершается.** §13: без оболочки
оно не нужно и не должно оставаться висеть. Отдельного «спящего режима» нет
намеренно: ядро, пережившее свою оболочку, — это процесс, который никто не
закроет.
"""

import contextvars
import secrets
import threading
import time
from typing import Any, Callable

from core import settings_schema
from core.confirmations import ConfirmationLedger
from core.protocol import ALL_EVENTS
from core.wire.data import DataSender
from core.wire.envelope import Envelope, FrameDecoder, IdGenerator, encode_frame
from core.wire.errors import (ERROR_UNKNOWN_METHOD, ProtocolFault, fault,
                              make)
from core.wire.events import StreamSender, event, validate_event
from core.wire.handshake import CORE_CAPABILITIES, Session, Side
from core.wire.liveness import Liveness, VolatileState
from core.wire.permissions import PermissionChannel
from core.wire.tasks import Registry
from core.trace import trace_scope
from core.wire.transport import Channels, TransportClosed


class ProtocolServer:
    """Ядро как собеседник: разбирает запросы, шлёт события."""

    def __init__(self, engine, channels: Channels, *,
                 versions=(1,), capabilities=None,
                 app_version: str = "4.0.0",
                 clock: Callable[[], float] = time.time,
                 on_stop: Callable[[], None] | None = None):
        self.engine = engine
        self.channels = channels
        self.clock = clock
        self.session = Session(side=Side.CORE, versions=list(versions),
                               capabilities=tuple(capabilities
                                                  or CORE_CAPABILITIES),
                               app_version=app_version)
        self.ids = IdGenerator("c-")
        self.decoder = FrameDecoder()
        self.liveness = Liveness(clock=clock)

        # Журнал подтверждений берётся у ядра, а не заводится свой: иначе
        # канал разрешений выписывал бы подтверждения, которых исполнитель
        # не знает, — и опасное действие не проходило бы никогда.
        runner = getattr(engine, "_tools", None)
        ledger = getattr(runner, "_confirmations", None)
        self.permissions = PermissionChannel(
            ledger=ledger or ConfirmationLedger(clock=clock), clock=clock)
        self.tasks = Registry(self.ids)
        self.data = DataSender()
        self.text = StreamSender(self.ids)
        self.volatile = VolatileState(
            permissions=self.permissions, tasks=self.tasks,
            data_streams=self.data, text_streams=self.text,
            session=self.session)

        self._send_lock = threading.Lock()
        self._running = False
        self._on_stop = on_stop
        self.stopped_because = ""
        self._subscribe()

    # -- события ядра --------------------------------------------------------

    def _subscribe(self) -> None:
        """
        Подписаться на все события ядра разом.

        Именно все, а не перечисленные руками: перечень живёт в
        `core/protocol.py`, сверен с каталогом провода и со спецификацией, и
        второй его копии здесь быть не должно — она разошлась бы первой.
        """
        for name in ALL_EVENTS:
            self.engine.bus.on(name, self._make_forwarder(name))

    def _make_forwarder(self, name: str):
        def forward(payload: dict) -> None:
            try:
                self.send(event(name, dict(payload or {}),
                                id=self.ids.next()))
            except ProtocolFault as exc:
                # Событие с неверной нагрузкой — дефект ядра. Роняет себя,
                # но не сессию: собеседник не виноват, что мы ошиблись.
                self._log_broken(name, exc)
            except TransportClosed:
                self.stop("канал закрыт при отправке события")
        return forward

    def _log_broken(self, name: str, exc: Exception) -> None:
        from core.logging_setup import get_logger
        get_logger("wire").error("Событие %s не отправлено: %s", name, exc)

    # -- отправка ------------------------------------------------------------

    def send(self, envelope: Envelope) -> Envelope:
        with self._send_lock:
            self.channels.control.send(encode_frame(envelope))
        return envelope

    # -- приём ---------------------------------------------------------------

    def serve_forever(self) -> str:
        """
        Читать канал, пока он жив. Возвращает причину остановки.

        Обрыв — не ошибка, а обычное завершение: оболочка закрылась, и ядру
        больше нечего делать.
        """
        self._running = True
        try:
            while self._running:
                try:
                    chunk = self.channels.control.recv()
                except TransportClosed as exc:
                    return self.stop(f"оболочка закрыла канал: {exc}")
                if chunk == b"":
                    continue            # тишина, а не конец: см. Transport.recv
                self.liveness.note_traffic()
                for message in self.decoder.feed(chunk):
                    self.dispatch(message)
        finally:
            self.channels.close()
        return self.stopped_because or "остановлено"

    def stop(self, why: str = "остановлено") -> str:
        if self._running:
            self._running = False
            self.stopped_because = why
            if self._on_stop is not None:
                self._on_stop()
        return why

    def dispatch(self, message: Envelope) -> list[Envelope]:
        """Обработать одно сообщение и отправить всё, что положено в ответ."""
        out: list[Envelope] = []
        with trace_scope(message.trace_id):
            method = message.method or ""
            try:
                self.session.check_incoming(method)
                handler = self._handlers().get(method)
                if handler is None:
                    raise fault(ERROR_UNKNOWN_METHOD,
                                f"метод {method!r} ядром не обслуживается",
                                method=method)
                payload = handler(message)
            except ProtocolFault as exc:
                out.append(self.send(
                    message.fail(exc.error, id=self.ids.next())))
                return out
            except Exception as exc:                    # noqa: BLE001
                self._log_broken(method, exc)
                out.append(self.send(message.fail(
                    make("internal", "Внутренняя ошибка ядра."),
                    id=self.ids.next())))
                return out

            if payload is not None:
                out.append(self.send(
                    message.reply(payload, id=self.ids.next())))
        return out

    # -- методы --------------------------------------------------------------

    def _handlers(self) -> dict[str, Callable[[Envelope], Any]]:
        return {
            "hello": self._hello,
            "ping": lambda m: {},
            "pong": lambda m: None,
            "core.shutdown": self._shutdown,
            "command.handle": self._command_handle,
            "command.run_by_id": self._command_by_id,
            "speech.listen_once": self._listen_once,
            "speech.set_always_listen": self._set_always_listen,
            "speech.say": self._say,
            "settings.get": self._settings_get,
            "settings.set": self._settings_set,
            "settings.describe": self._settings_describe,
            "reminders.list": self._reminders_list,
            "reminders.cancel": self._reminders_cancel,
            "commands.list": self._commands_list,
            "commands.save": self._commands_save,
            "commands.delete": self._commands_delete,
            "commands.set_enabled": self._commands_set_enabled,
            "commands.export": self._commands_export,
            "commands.import": self._commands_import,
            "history.list": self._history_list,
            "history.clear": self._history_clear,
            "history.export": self._history_export,
            "task.cancel": self._task_cancel,
            "plugins.install": self._plugins_install,
        }

    def _hello(self, message: Envelope) -> dict:
        return self.session.handle_hello(message.payload)

    def _shutdown(self, message: Envelope) -> dict:
        self.stop("оболочка попросила завершиться")
        return {"ok": True}

    def _command_handle(self, message: Envelope) -> dict:
        """
        Ответ — «принято», а не результат.

        Результат придёт событием: команда может думать секундами и сказать
        по дороге несколько вещей, и всё, кроме последней, потерялось бы.
        """
        text = str(message.payload.get("text", ""))
        self.engine.handle_command_async(
            text,
            require_wake=bool(message.payload.get("require_wake", False)),
            source=str(message.payload.get("source", "typed")))
        return {"accepted": True}

    def _command_by_id(self, message: Envelope) -> dict:
        self.engine.run_command_by_id(str(message.payload.get("command_id")))
        return {"accepted": True}

    def _listen_once(self, message: Envelope) -> dict:
        # Контекст копируется, чтобы события прослушивания попали в ту же
        # цепочку, что и запрос: новый поток начинается с пустого контекста.
        ctx = contextvars.copy_context()
        threading.Thread(target=ctx.run, args=(self.engine.listen_once,),
                         daemon=True).start()
        return {"accepted": True}

    def _set_always_listen(self, message: Envelope) -> dict:
        self.engine.set_always_listen(bool(message.payload.get("enabled")))
        return {"enabled": bool(self.engine.is_always_listen())}

    def _say(self, message: Envelope) -> dict:
        self.engine.say(str(message.payload.get("text", "")))
        return {"accepted": True}

    # -- настройки -----------------------------------------------------------

    def _settings(self):
        return getattr(self.engine, "_settings", None)

    def _settings_get(self, message: Envelope) -> dict:
        keys = message.payload.get("keys") or []
        store = self._settings()
        schema = settings_schema.describe(keys)
        # Секретное и устаревшее наружу не уходит: config_version и first_run
        # — состояние хранилища, а theme и accent заменены отделками (R08).
        # Данные при этом целы, просто оболочке они больше не нужны.
        return {"values": {k: store.get(k) for k in keys
                           if not schema.get(k, {}).get("secret")
                           and not schema.get(k, {}).get("obsolete")}}

    def _settings_set(self, message: Envelope) -> dict:
        """
        Записать значения и отчитаться по каждому.

        Отчёт по ключу, а не одно «получилось» на всю посылку: из десяти
        значений одно может не пройти, и сказать про это «не сохранилось»
        значит не сказать ничего. Вердикты — кодами каталога D05, чтобы
        оболочка ветвилась по ним, а не по тексту.

        Предупреждение — не отказ. «Адрес модели не локальный» значит, что
        значение принято и записано, а человеку сказано, чем это обернётся:
        решать ему, а не нам.
        """
        values = message.payload.get("values") or {}
        store = self._settings()
        verdicts: dict[str, dict] = {}
        accepted: dict[str, Any] = {}
        for key, value in values.items():
            ok, code, text = settings_schema.validate(key, value)
            verdicts[key] = {"accepted": ok, "code": code, "message": text}
            if ok:
                accepted[key] = value
        if accepted:
            with store.transaction():
                for key, value in accepted.items():
                    store.set(key, value)
        return {"values": {k: store.get(k) for k in accepted},
                "verdicts": verdicts}

    def _settings_describe(self, message: Envelope) -> dict:
        """
        Смысл значений, но **не** их вид (ADR 0006).

        `layout` отдаётся как `null` явно, а не опускается: отсутствие ключа
        читалось бы как «ещё не сделали», тогда как `null` читается как «это
        не наше дело» — что и есть действительное положение вещей.
        """
        keys = message.payload.get("keys") or None
        return {
            "schema": settings_schema.describe(keys),
            "layout": None,
            "note": "раскладку описывает оболочка: ADR 0006",
        }

    # -- напоминания ---------------------------------------------------------

    def _reminders(self):
        return getattr(self.engine, "_reminders", None)

    def _reminders_list(self, message: Envelope) -> dict:
        store = self._reminders()
        return {"items": [dict(item) for item in store.active()]}

    def _reminders_cancel(self, message: Envelope) -> dict:
        store = self._reminders()
        if message.payload.get("all"):
            return {"cancelled": int(store.clear_active())}
        item_id = message.payload.get("id")
        return {"cancelled": 1 if store.remove(item_id) else 0}

    # -- свои команды пользователя -------------------------------------------

    def _commands(self):
        return getattr(self.engine, "_cmd_store", None)

    def _commands_list(self, message: Envelope) -> dict:
        return {"items": [dict(c) for c in self._commands().all()]}

    def _commands_save(self, message: Envelope) -> dict:
        """
        Создать или изменить — один метод, а не два.

        Для оболочки это одно действие: человек правит карточку и нажимает
        «сохранить». Разделять по тому, есть ли уже идентификатор, значит
        заставлять её знать то, что знает хранилище.
        """
        store = self._commands()
        command = dict(message.payload.get("command") or {})
        if command.get("id"):
            store.update(command)
        else:
            # Номер назначает ядро, а не оболочка. Идентификатор, пришедший
            # снаружи, — это чужое право решать, какая команда какая; та же
            # причина, по которой confirmation_id выпускает ядро (§11).
            command["id"] = "cmd_" + secrets.token_hex(3)
            store.add(command)
        return {"command": dict(command)}

    def _commands_delete(self, message: Envelope) -> dict:
        # Хранилище не говорит, удалило ли оно что-нибудь, поэтому считаем
        # сами: «удалено» и «такой не было» — разные ответы для оболочки.
        store = self._commands()
        was = len(store.all())
        store.remove(str(message.payload.get("id", "")))
        return {"deleted": len(store.all()) < was}

    def _commands_set_enabled(self, message: Envelope) -> dict:
        store = self._commands()
        store.set_enabled(str(message.payload.get("id", "")),
                          bool(message.payload.get("enabled")))
        return {"items": [dict(c) for c in store.all()]}

    def _commands_export(self, message: Envelope) -> dict:
        """
        Отдать команды, а не записать файл.

        Файл выбирает и пишет оболочка: диалог выбора места — её работа, а
        ядро её и не умеет. Ядро отдаёт содержимое.
        """
        return {"commands": [dict(c) for c in self._commands().all()]}

    def _commands_import(self, message: Envelope) -> dict:
        """
        Принять команды. Существующие не затираются молча.

        Совпадение по идентификатору значит, что команда уже есть, и импорт
        её пропускает: «перенести на другую машину» и «затереть то, что
        человек уже настроил» — разные намерения, и по умолчанию верно
        второе не делать.
        """
        store = self._commands()
        known = {c.get("id") for c in store.all()}
        added, skipped = 0, 0
        for command in message.payload.get("commands") or []:
            if not isinstance(command, dict):
                skipped += 1
                continue
            if command.get("id") in known:
                skipped += 1
                continue
            store.add(dict(command))
            added += 1
        return {"added": added, "skipped": skipped}

    # -- история разговора ----------------------------------------------------

    def _history(self):
        return getattr(self.engine, "_history", None)

    def _history_list(self, message: Envelope) -> dict:
        items = self._history().all()
        limit = message.payload.get("limit")
        if isinstance(limit, int) and not isinstance(limit, bool) and limit > 0:
            items = items[-limit:]
        return {"items": [dict(i) for i in items], "total": len(items)}

    def _history_clear(self, message: Envelope) -> dict:
        store = self._history()
        was = len(store.all())
        store.clear()
        return {"cleared": was}

    def _history_export(self, message: Envelope) -> dict:
        return {"items": [dict(i) for i in self._history().all()]}

    # -- плагины --------------------------------------------------------------

    def _plugins_install(self, message: Envelope) -> dict:
        """
        Установка плагина: пока отвечает честным отказом.

        Плагин в 4.0 живёт в отдельном процессе (`4.0-H07`), и установка —
        работа блока H целиком. Метод объявлен здесь, чтобы страница плагинов
        писалась под настоящий контракт, а не под будущий: отвечать «ещё нет»
        честнее, чем не иметь метода и делать вид, что возможность не
        терялась.
        """
        raise fault("internal",
                    "Установка плагинов появится вместе с блоком H (4.0-H).")

    # -- задачи --------------------------------------------------------------

    def _task_cancel(self, message: Envelope) -> dict:
        return self.tasks.cancel(str(message.payload.get("task_id", "")))

    # -- обрыв ---------------------------------------------------------------

    def on_disconnect(self) -> dict[str, int]:
        """
        Оболочка пропала: сбросить всё летучее (§13).

        Ядро после этого завершается — см. заголовок модуля.
        """
        return self.volatile.reset()
