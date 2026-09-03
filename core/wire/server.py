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
        #: Переданные снаружи не переcобираются: проверка ставила их нарочно.
        self._speech_given = (recogniser is not None, synthesiser is not None)
        store = getattr(engine, "_settings", None)
        self._speech_wanted = (
            str((store.get("stt_engine", "disabled") if store else "disabled")
                or "disabled"),
            str((store.get("tts_engine", "silent") if store else "silent")
                or "silent"))
        self.segmenter = speech.Segmenter()
        self._speech_stream = 0
        self._speech_rate = 0

        #: Куда девать принятый звук, если распознавание не нужно.
        self.on_audio = None

        # Голос ядра уходит в оболочку, а не в местный динамик (4.0-E04).
        engine.voice_out = self._speak
        # Машину трогает оболочка (ADR 0009). Ядро решает, что сделать, и
        # просит; своих системных вызовов у него больше нет.
        engine.system_out = self.do_system
        # Индекс программ — данные операционной системы, и живут они в
        # оболочке (ADR 0009). Ядро спрашивает и сопоставляет.
        engine.apps_source = self.fetch_apps
        engine.launch_out = self.launch_app
        # Опасное подтверждается окном, а не только словами (4.0-F11).
        engine.on_question = self._on_question

        #: Наши запросы, ждущие ответа оболочки. Сервер до сих пор умел
        #: только отвечать; чтобы спросить (§11), надо уметь и дождаться.
        self._awaiting: dict[str, Callable[[Envelope], None]] = {}

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

        # Ответ на наш собственный запрос — не метод, и искать для него
        # обработчик значило бы ответить «неизвестный метод» на собственный
        # вопрос.
        if message.type in ("response", "error") and message.correlation_id:
            waiting = self._awaiting.pop(message.correlation_id, None)
            if waiting is not None:
                with trace_scope(message.trace_id):
                    waiting(message)
            return out

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
            "settings.options": self._settings_options,
            "reminders.list": self._reminders_list,
            "reminders.cancel": self._reminders_cancel,
            "reminders.create": self._reminders_create,
            "commands.list": self._commands_list,
            "commands.kinds": self._commands_kinds,
            "commands.save": self._commands_save,
            "commands.delete": self._commands_delete,
            "commands.set_enabled": self._commands_set_enabled,
            "commands.export": self._commands_export,
            "commands.import": self._commands_import,
            "history.list": self._history_list,
            "history.clear": self._history_clear,
            "history.export": self._history_export,
            "task.cancel": self._task_cancel,
            "plugins.list": self._plugins_list,
            "plugins.set_enabled": self._plugins_set_enabled,
            "plugins.page": self._plugins_page,
            "plugins.action": self._plugins_action,
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
            ok, code, text = settings_schema.validate(key, value, store)
            verdicts[key] = {"accepted": ok, "code": code, "message": text}
            if ok:
                accepted[key] = value
        if accepted:
            with store.transaction():
                for key, value in accepted.items():
                    store.set(key, value)
                self._settle_voice(store, accepted, verdicts)
                if "ui_language" in accepted:
                    # Язык — не та настройка, ради которой перезапускают
                    # программу. Реплики переключаются здесь, слова
                    # интерфейса — в оболочке, каждый у себя.
                    from core import i18n
                    i18n.set_language(str(accepted["ui_language"]))
                if "log_level" in accepted:
                    # Уровень журнала умел применяться на лету (`apply_settings`),
                    # но звал его тот, кто менял, — экран настроек 3.1.0.
                    # Та же потеря, что и с сохранением: экран уехал,
                    # вызов остался.
                    from core import logging_setup
                    logging_setup.apply_settings()
                # Записать на диск. `set()` только помечает группу
                # изменившейся, и в 3.1.0 сохранял тот, кто менял, — экран
                # настроек. Экран уехал в другой процесс, а вызов остался
                # там: настройка держалась до конца работы ядра и пропадала.
                # Пишем внутри транзакции, чтобы между изменением и записью
                # не встрял чужой поток.
                store.save()
        return {"values": {k: store.get(k) for k in accepted},
                "verdicts": verdicts}

    @staticmethod
    def _settle_voice(store, accepted: dict, verdicts: dict) -> None:
        """
        Сменился движок — сменить и голос, если старый ему чужой.

        У каждого движка своя нумерация голосов: `ru-RU-SvetlanaNeural` для
        одного и `default` для другого. Оставить прежнее значение — значит
        оставить настройку, которая навсегда показывает «сейчас недоступно»
        и ничего не озвучивает; заставлять человека выбирать голос заново
        после каждой смены движка — значит требовать шага, который мы можем
        сделать сами и почти всегда угадаем.

        Об этом говорится вслух: тихо переписанная настройка — та самая
        неожиданность, которую человек потом ищет глазами.
        """
        if "tts_engine" not in accepted:
            return
        choices = settings_schema.options_for("voice", store)
        if not choices or store.get("voice") in {c["value"] for c in choices}:
            return
        picked = choices[0]
        store.set("voice", picked["value"])
        verdicts["tts_engine"] = dict(verdicts["tts_engine"],
                                      message=f"Голос переключён на "
                                              f"«{picked['title']}».")

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

    def _settings_options(self, message: Envelope) -> dict:
        """
        Какие значения ключ принимает сейчас, на этой машине.

        Отдельный метод, а не поле в схеме: схема описывает то, что верно
        всегда, а этот список меняется от установки модели и даже от того,
        какой движок выбран сейчас. Держать изменчивое рядом с постоянным
        значит однажды закешировать первое вместе со вторым.
        """
        store = self._settings()
        keys = message.payload.get("keys") or []
        return {"options": {key: settings_schema.options_for(key, store)
                            for key in keys}}

    # -- напоминания ---------------------------------------------------------

    def _reminders(self):
        return getattr(self.engine, "_reminders", None)

    def _reminders_list(self, message: Envelope) -> dict:
        store = self._reminders()
        return {"items": [dict(item) for item in store.active()]}

    def _reminders_create(self, message: Envelope) -> dict:
        """
        Завести напоминание из окна.

        Голосом это делается разбором фразы («напомни в семь про хлеб»), и
        поначалу казалось, что окну хватит того же пути. Не хватает:
        человек у экрана выбирает время в поле, а не проговаривает его
        словами, и заставлять оболочку составлять русскую фразу ради
        обратного разбора — значит проверять разбор вместо намерения.

        Время приходит меткой, а не словами: у оболочки есть календарь, и
        часовой пояс у неё тот же, что у ядра, — оба живут на одной машине.
        """
        store = self._reminders()
        if store is None:
            raise fault("internal", "Напоминания недоступны.")

        text = str(message.payload.get("text", "")).strip()
        if not text:
            raise fault("protocol.invalid_payload",
                        "Напоминание без текста не о чем.")
        try:
            fire_at = float(message.payload.get("fire_at", 0))
        except (TypeError, ValueError):
            fire_at = 0.0
        if fire_at <= 0:
            raise fault("protocol.invalid_payload",
                        "Нужно время, когда напомнить.")

        # Вид влияет только на то, как напоминание назовут человеку
        # («Будильник», «Таймер», «Напоминание»), и оболочка вправе его не
        # знать: заведённому из окна подходит обычное напоминание.
        kind = str(message.payload.get("kind", "reminder") or "reminder")
        # События о заведении нет намеренно: список запросит тот, кто
        # завёл, и он же его показывает. Событие понадобилось бы, если бы
        # напоминания заводились помимо оболочки, — но голосом их заводит
        # та же оболочка тем же соединением.
        return {"item": dict(store.add(kind, fire_at, text))}

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

    def _commands_kinds(self, message: Envelope) -> dict:
        """
        Из чего команда бывает сделана.

        Имена вещей приходят оттуда, где вещи живут (то же правило, что у
        `settings.options`): виды команд и системные действия перечисляет
        ядро, потому что выполнять их ему. Оболочка, знающая этот список
        наизусть, разошлась бы с ядром молча — и показала бы человеку
        действие, которого больше нет, или спрятала бы новое.

        Здесь же сказано, какое действие **необратимо**: подтверждение
        спрашивает ядро (§11), но человек должен видеть это ещё в
        конструкторе, а не узнать при первом срабатывании.
        """
        from voice import user_commands

        return {
            "kinds": [{"value": kind, "title": title, "icon": icon}
                      for kind, title, icon in user_commands.COMMAND_TYPES],
            "actions": [{"value": action, "title": title,
                         "destructive": action
                         in user_commands.DESTRUCTIVE_ACTIONS}
                        for action, title in user_commands.SYSTEM_ACTIONS],
            "matches": [{"value": "contains", "title": "Фраза встречается"},
                        {"value": "exact", "title": "Фраза целиком"}],
        }

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

    def _plugin_manager(self):
        return getattr(self.engine, "_plugins", None)

    @staticmethod
    def _plugin_state(plugin_id: str, loaded) -> dict:
        """
        Что оболочка знает о плагине.

        Сбойный плагин показывается вместе с причиной, а не исчезает из
        списка: человек поставил его сам и должен увидеть, почему он не
        работает. Исчезнувший плагин выглядит как «я его не ставил».
        """
        manifest = loaded.manifest
        return {
            "plugin_id": plugin_id,
            "name": manifest.name,
            "version": manifest.version,
            "author": manifest.author,
            "description": manifest.description,
            "icon": manifest.icon,
            "enabled": bool(loaded.enabled),
            "broken": bool(loaded.error),
            "error": loaded.error or "",
            "has_page": bool(loaded.instance is not None
                             and loaded.error is None),
        }

    def _plugins_list(self, message: Envelope) -> dict:
        manager = self._plugin_manager()
        if manager is None:
            return {"items": []}
        pages = {pid for pid, _ in manager.page_plugins()}
        items = []
        for plugin_id, loaded in manager.plugins.items():
            state = self._plugin_state(plugin_id, loaded)
            state["has_page"] = plugin_id in pages
            items.append(state)
        return {"items": items}

    def _plugins_set_enabled(self, message: Envelope) -> dict:
        """
        Включить или выключить плагин.

        Возвращается **состояние после** изменения, а не «принято»: плагин
        может отказаться загружаться, и тогда «включено» будет неправдой.
        Оболочка рисует то, что есть, а не то, что просили.
        """
        manager = self._plugin_manager()
        plugin_id = str(message.payload.get("plugin_id", ""))
        if manager is None or plugin_id not in manager.plugins:
            raise fault("plugin.not_found", f"Плагин «{plugin_id}» не найден.")

        manager.toggle(plugin_id, bool(message.payload.get("enabled", False)))
        loaded = manager.plugins[plugin_id]
        return {"plugin": self._plugin_state(plugin_id, loaded)}

    def _plugins_page(self, message: Envelope) -> dict:
        """
        Декларативное описание страницы плагина.

        Плагин описывает страницу списком элементов, а рисует их оболочка.
        Так было решено ещё в 3.1.0 (`plugins/page_spec.py`), когда плагин
        перестал возвращать готовый виджет, — и ровно поэтому страница
        плагина рисуется в другом процессе на другом языке без единой
        правки в самом плагине.
        """
        manager = self._plugin_manager()
        plugin_id = str(message.payload.get("plugin_id", ""))
        if manager is None or plugin_id not in manager.plugins:
            raise fault("plugin.not_found", f"Плагин «{plugin_id}» не найден.")

        spec = manager.get_plugin_page_spec(plugin_id)
        return {"plugin_id": plugin_id,
                "elements": [element.to_dict() for element in spec]}

    def _plugins_action(self, message: Envelope) -> dict:
        """
        Нажата кнопка на странице плагина; в ответ — новая страница.

        Новое описание возвращается тем же ответом, а не событием: кнопка
        меняет то, что нарисовано рядом с ней, и заставлять оболочку
        спрашивать страницу второй раз значило бы показать её устаревшей
        ровно на один круг.
        """
        manager = self._plugin_manager()
        plugin_id = str(message.payload.get("plugin_id", ""))
        if manager is None or plugin_id not in manager.plugins:
            raise fault("plugin.not_found", f"Плагин «{plugin_id}» не найден.")

        manager.dispatch_action(plugin_id,
                                str(message.payload.get("action", "")),
                                message.payload.get("value"))
        spec = manager.get_plugin_page_spec(plugin_id)
        return {"plugin_id": plugin_id,
                "elements": [element.to_dict() for element in spec]}

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

    # -- вопрос человеку (4.0-F11, §11) ---------------------------------------

    def ask_shell(self, method: str, payload: dict,
                  on_answer: Callable[[Envelope], None]) -> Envelope:
        """Задать вопрос оболочке и запомнить, кто ждёт ответа."""
        request = Envelope.request(method, payload, id=self.ids.next())
        self._awaiting[request.id] = on_answer
        return self.send(request)

    def ask_shell_sync(self, method: str, payload: dict,
                       timeout: float = 10.0) -> dict:
        """
        Спросить оболочку и дождаться ответа.

        Нужен потому, что системное действие выполняется **внутри** разбора
        команды: инструмент «прибавь громкость» обязан вернуть исход, а не
        «я попросил». Асинхронный `ask_shell` для этого не годится — он
        оставляет вызывающего без ответа.

        Ждём в том потоке, который обрабатывает команду, а не в приёмном:
        приёмный поток здесь и отвечает, и заблокировать его значило бы
        ждать ответа тем самым потоком, который его принесёт.
        """
        done = threading.Event()
        got: dict = {}

        def answered(reply: Envelope) -> None:
            got["reply"] = reply
            done.set()

        # Проверка на своей стороне: оболочка без Windows не объявит
        # `system`, и узнать об этом лучше здесь, чем по молчанию.
        self.session.check_outgoing(method)
        request_id = self.ask_shell(method, payload, answered).id
        if not done.wait(timeout):
            self._awaiting.pop(request_id, None)
            raise fault("internal", "Оболочка не ответила вовремя.")

        reply = got["reply"]
        if reply.type == "error":
            raise ProtocolFault(reply.payload.get("code", "internal"),
                                reply.payload.get("message", ""))
        return dict(reply.payload)

    def fetch_apps(self, refresh: bool = False) -> list:
        """
        Спросить у оболочки индекс установленных программ.

        Сопоставление имени с записью остаётся здесь: «телеграм» → Telegram
        это транслитерация и нечёткое совпадение, то есть язык, а язык —
        предмет ядра. Оболочка отдаёт факты о системе, ядро решает, что
        человек имел в виду (ADR 0009).
        """
        try:
            answer = self.ask_shell_sync("apps.index", {"refresh": refresh},
                                         timeout=60.0)
        except ProtocolFault:
            # Оболочка без индекса — не повод падать: команда «открой
            # телеграм» ответит «не нашла», а остальное будет работать.
            return []
        return list(answer.get("entries") or [])

    def launch_app(self, launch: str, kind: str = "file") -> tuple[bool, str]:
        """Попросить оболочку запустить найденное."""
        try:
            answer = self.ask_shell_sync("apps.launch",
                                         {"launch": launch, "kind": kind},
                                         timeout=30.0)
        except ProtocolFault as exc:
            return False, str(exc)
        return bool(answer.get("ok")), str(answer.get("reason", ""))

    def do_system(self, action: str) -> tuple[bool, str]:
        """
        Попросить оболочку сделать системное действие.

        Слова остаются здесь: «Прибавила громкость» — реплика Рины
        (ADR 0007), а оболочка отвечает фактом. Поэтому наружу уходит пара
        «получилось, подробность», а не готовое предложение.
        """
        try:
            answer = self.ask_shell_sync("system.do", {"action": action})
        except ProtocolFault as exc:
            return False, str(exc)
        return bool(answer.get("ok")), str(answer.get("detail", ""))

    def _on_question(self, question) -> None:
        """
        Ядро задало вопрос — показать его человеку окном (§11).

        Спрашивается **только необратимое**: у уточняющего «какой из трёх
        телеграмов» нет ни опасности, ни предпросмотра, и вырывать его в
        модальное окно значило бы прерывать разговор ради выбора, который
        удобнее сделать словами.

        Голосовой путь при этом не отменяется: человек может ответить «да»
        вслух, и вопрос закроется сам — окно тогда просто перестанет быть
        нужным.
        """
        if question.kind not in ("confirm_action", "confirm_command"):
            return
        if not self.session.ready:
            return
        if "permissions" not in self.session.peer_capabilities:
            return          # оболочка не умеет спрашивать — останется голосом

        asked = question.to_dict()
        action = asked.get("action") or ""
        command_id = asked.get("command_id") or ""

        # Предпросмотр — то, что человеку показывают вместо названия
        # действия. §11 требует показать, **что именно произойдёт**:
        # «Выключить компьютер?» человек успевает осознать, а «power_action»
        # не значит ничего.
        if action:
            from voice import system_control

            preview = system_control.confirm_question(action)
        else:
            preview = "Выполнить сохранённую команду?"

        self.ask_shell("permission.request", {
            "request_id": question.confirmation_id or "",
            "permission": "system.power" if action else "process.launch",
            "action": action or command_id,
            "reason": "Сказано голосом" if action else "Запуск своей команды",
            "preview": preview,
            "ttl": int(getattr(question, "TTL", 0)
                       or getattr(question, "ttl", 0) or 60),
        }, self._on_permission_answer)

    def _on_permission_answer(self, message: Envelope) -> None:
        """
        Ответ оболочки. Отказ по умолчанию: всё, кроме явного «да», — «нет».
        """
        granted = (message.type == "response"
                   and message.payload.get("granted") is True)
        self.engine.answer_question(granted)

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

    def _voice_follows_settings(self) -> None:
        """
        Пересобрать синтез и распознавание, если движок сменили.

        Иначе выбор в настройках начинал действовать только после
        перезапуска ядра: человек ставит Edge, слышит тишину и решает, что
        сломано. Настройка, которая «применится когда-нибудь», — это не
        настройка, а обещание; помеченные `restart_required` говорят об
        этом честно, а эти две ничего такого не обещали.
        """
        store = self._settings()
        if store is None:
            return
        # Сравнивается то, что попросили, а не то, что получилось: движок,
        # которого ядро не умеет, даёт «выключено», и сверка по имени
        # пересобирала бы его на каждой реплике.
        wanted = (str(store.get("stt_engine", "disabled") or "disabled"),
                  str(store.get("tts_engine", "silent") or "silent"))
        if wanted == self._speech_wanted:
            return
        self._speech_wanted = wanted
        if not self._speech_given[1]:
            self.synthesiser = speech.synthesiser_for(store)
        if not self._speech_given[0]:
            self.recogniser = speech.recogniser_for(store)

    def _speak(self, text: str) -> None:
        """
        Синтезировать и отправить оболочке.

        Синтез в ядре, воспроизведение в оболочке: модели живут там, где
        ML-экосистема, а звук — там, где низкая задержка и нативное аудио.
        """
        self._voice_follows_settings()
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

        # Частота объявляется при открытии потока, поэтому смена движка —
        # это новый поток, а не продолжение старого. Иначе речь на 24000
        # поехала бы в поток, объявленный на 22050, и Рина заговорила бы
        # ниже и медленнее, чем должна.
        if self._speech_stream and self._speech_rate != sample_rate:
            self.send(Envelope.request(
                "stream.close", {"stream_id": self._speech_stream},
                id=self.ids.next()))
            self.data.close_stream(self._speech_stream)
            self._speech_stream = 0

        if self._speech_stream == 0:
            self._speech_rate = sample_rate
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
