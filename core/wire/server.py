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

from core import settings_schema, speech
from core.confirmations import ConfirmationLedger
from core.protocol import ALL_EVENTS
from core.wire.data import (DataFrameDecoder, DataReceiver, DataSender,
                            capability_for_kind)
from core.wire.envelope import Envelope, FrameDecoder, IdGenerator, encode_frame
from core.wire.errors import (ERROR_INVALID_PAYLOAD, ERROR_UNKNOWN_METHOD,
                              ProtocolFault, fault, make)
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
                 on_stop: Callable[[], None] | None = None,
                 recogniser=None, synthesiser=None):
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

        #: Открытые входящие потоки: номер -> что про него известно.
        self.incoming: dict[int, dict] = {}
        #: Сколько байт разрешаем держать в полёте. Небольшое окно: звук
        #: приходит непрерывно, и большой кредит означает большую задержку
        #: между «сказал» и «услышала».
        self.credit_window = 64 * 1024
        self.receiver = None
        #: Распознавание и синтез. Передаются снаружи, чтобы их можно было
        #: подменить в проверке: настоящие модели ставятся не на всякой
        #: машине, а провод обязан проверяться везде.
        self.recogniser = recogniser or speech.recogniser_for(
            getattr(engine, "_settings", None) or {})
        self.synthesiser = synthesiser or speech.synthesiser_for(
            getattr(engine, "_settings", None) or {})
        self.segmenter = speech.Segmenter()
        self._speech_stream = 0

        #: Куда девать принятый звук, если распознавание не нужно.
        self.on_audio = None

        # Голос ядра уходит в оболочку, а не в местный динамик (4.0-E04).
        engine.voice_out = self._speak

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

        # Канал данных читает свой поток — в этом и был смысл двух труб:
        # всплеск звука не должен задерживать команду. Запускается здесь, а
        # не снаружи: снаружи его заводили раньше, чем поднимался флаг
        # работы, и поток умирал на первой же проверке условия, молча.
        if self.channels.data is not None:
            threading.Thread(target=self.pump_data, name="rina-data",
                             daemon=True).start()

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
            "stream.open": self._stream_open,
            "stream.close": self._stream_close,
            "stream.credit": self._stream_credit,
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

    # -- потоки данных (4.0-D07, D08; сторона ядра для 4.0-F09) ---------------

    def _stream_open(self, message: Envelope) -> dict:
        """
        Открыть двоичный поток и сразу выдать первый кредит.

        Начальный кредит — ноль (§8), и пока приёмник его не выдаст,
        отправитель молчит. Выдаём здесь же: ядро готово принимать ровно с
        того мгновения, как согласилось открыть поток, и заставлять оболочку
        ждать отдельного сообщения не за чем.
        """
        stream_id = message.payload.get("stream_id")
        kind = str(message.payload.get("kind", ""))
        if not isinstance(stream_id, int) or isinstance(stream_id, bool):
            raise fault(ERROR_INVALID_PAYLOAD, "у потока обязан быть номер")

        capability = capability_for_kind(kind)
        if capability not in self.session.capabilities \
                and capability not in self.session.peer_capabilities:
            raise fault(ERROR_UNKNOWN_METHOD,
                        f"вид потока {kind!r} в этой сессии не объявлен",
                        kind=kind, capability=capability)

        self.incoming[stream_id] = {
            "kind": kind,
            "format": dict(message.payload.get("format") or {}),
            "bytes": 0,
            "frames": 0,
        }
        self.receiver = self.receiver or DataReceiver(window=self.credit_window)
        granted = self.credit_window
        self.send(Envelope.event("stream.credit", {"bytes": granted},
                                 id=self.ids.next(), stream_id=stream_id))
        return {"accepted": True, "credit": granted}

    def _stream_close(self, message: Envelope) -> dict:
        stream_id = message.payload.get("stream_id")
        state = self.incoming.pop(stream_id, None)
        return {"closed": state is not None,
                "bytes": (state or {}).get("bytes", 0)}

    def _stream_credit(self, message: Envelope) -> dict:
        """Кредит от оболочки — для потоков, которые шлёт ядро (4.0-F10)."""
        stream_id = message.payload.get("stream_id")
        extra = int(message.payload.get("bytes") or 0)
        if stream_id in self.data.open and extra > 0:
            self.data.grant(stream_id, extra)
        return {"accepted": True}

    def pump_data(self) -> str:
        """
        Читать канал данных, пока он жив.

        Отдельный поток, потому что канал отдельный, — в этом и был смысл
        двух труб: всплеск звука не должен задерживать команду. Кредит
        выдаётся **по мере обработки**, а не получения: кредит за то, что
        лежит непрочитанным в буфере, и есть та неограниченная очередь,
        ради устранения которой схема существует.
        """
        if self.channels.data is None:
            return "канала данных нет"
        decoder = DataFrameDecoder()
        while self._running:
            try:
                chunk = self.channels.data.recv()
            except TransportClosed:
                return "канал данных закрыт"
            if chunk == b"":
                continue
            for frame in decoder.feed(chunk):
                self._on_data(frame)
        return "остановлено"

    def _on_data(self, frame) -> None:
        state = self.incoming.get(frame.stream_id)
        if state is None:
            # Поток, о котором не договаривались. Не обрыв: отправитель мог
            # не успеть узнать, что мы его закрыли.
            return
        state["bytes"] += len(frame.payload)
        state["frames"] += 1
        if state["kind"] == "audio.input":
            if self.on_audio is not None:
                self.on_audio(frame.stream_id, frame.payload, state["format"])
            self._hear(frame.payload)
        # Обработали — возвращаем кредит на обработанное.
        self.send(Envelope.event("stream.credit",
                                 {"bytes": len(frame.payload)},
                                 id=self.ids.next(),
                                 stream_id=frame.stream_id))

    # -- речь (4.0-E03, E04) --------------------------------------------------

    def _hear(self, pcm: bytes) -> None:
        """
        Накопить звук и распознать законченную фразу.

        Нарезка на фразы делается здесь, а не в оболочке: только рядом с
        распознаванием известно, сколько тишины считать паузой в
        предложении, а сколько концом фразы.

        Распознавание идёт в своём потоке: модель думает сотни миллисекунд,
        а на этом же потоке читается канал данных — задержка превратилась бы
        в пропущенный звук.
        """
        for phrase in self.segmenter.feed(pcm):
            threading.Thread(target=self._recognise, args=(phrase,),
                             name="rina-stt", daemon=True).start()

    def _recognise(self, phrase: bytes) -> None:
        with trace_scope():
            if not self.recogniser.available():
                # Молчать здесь нельзя: человек решит, что его не слышно, и
                # станет говорить громче.
                self.engine.bus.emit(
                    "assistant.error",
                    text="Распознавание недоступно: выберите модель в настройках.")
                return
            heard = self.recogniser.recognise(phrase)
            if not heard.ok:
                self.engine.bus.emit("assistant.error",
                                     text=f"Не удалось распознать: {heard.error}")
                return
            if not heard.text:
                return          # тишина — не ошибка и не повод сообщать
            self.engine.bus.emit("speech.recognized", text=heard.text)
            self.engine.handle_command_async(heard.text, source="voice")

    def _speak(self, text: str) -> None:
        """
        Синтезировать и отправить оболочке.

        Синтез в ядре, воспроизведение в оболочке: модели живут там, где
        ML-экосистема, а звук — там, где низкая задержка и нативное аудио.
        """
        if not self.synthesiser.available():
            return          # текст уже отправлен событием; голоса просто нет
        pcm = self.synthesiser.synthesize(
            text,
            voice=str(self._settings().get("voice", "") if self._settings()
                      else ""),
            rate=int((self._settings() or {}).get("speed", 100) or 100))
        if not pcm:
            return
        self.send_speech(pcm, self.synthesiser.sample_rate)

    def send_speech(self, pcm: bytes, sample_rate: int) -> None:
        """Отправить готовый звук оболочке кусками по каналу данных."""
        if self.channels.data is None:
            return
        if self._speech_stream == 0:
            self._speech_stream = 21
            self.data.open_stream(self._speech_stream, "audio.output")
            self.send(Envelope.request(
                "stream.open",
                {"stream_id": self._speech_stream, "kind": "audio.output",
                 "format": {"encoding": "pcm_s16le", "rate": sample_rate,
                            "channels": 1}},
                id=self.ids.next()))
            # Оболочка выдаст кредит, но ждать его молча нечестно по времени:
            # первый кусок речи должен уйти сразу. Даём себе кредит на один
            # ответ и дальше живём по выданному.
            self.data.grant(self._speech_stream, 512 * 1024)

        chunk = 8192
        for offset in range(0, len(pcm), chunk):
            piece = pcm[offset:offset + chunk]
            if self.data.available(self._speech_stream) < len(piece):
                break       # оболочка не успевает: обрывать речь честнее,
                            # чем копить её в памяти
            self.channels.data.send(self.data.send(self._speech_stream, piece))

    # -- обрыв ---------------------------------------------------------------

    def on_disconnect(self) -> dict[str, int]:
        """
        Оболочка пропала: сбросить всё летучее (§13).

        Ядро после этого завершается — см. заголовок модуля.
        """
        return self.volatile.reset()
