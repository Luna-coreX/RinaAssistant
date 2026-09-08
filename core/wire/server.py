"""
The protocol's server side: the core answers over the wire.

Plan item `4.0-E02`; the specification — all of it, and this is its first
real consumer.

Until now the `core/wire` package could assemble and parse messages but was
connected to nothing: the conformance suite talked to a reference core
written right beside it. Here the wire is joined to the real
`core/engine.py`.

**The core decides, the shell shows.** The answer to a command is not the
text of the reply but "accepted for handling": the reply itself will come as
an `assistant.response` event, when it appears. That is how 3.1.0 works too,
where a command may think for seconds and manage to say several things;
giving its result as the answer to the request would mean keeping the
request open all that time and losing everything but the last.

**The core's events pour into protocol events one for one.** That is exactly
why the `core/wire/events.py` catalogue was checked against
`core/protocol.py`: the transfer neither renames nor invents, or a third
list would join the two — a mapping table, which would also have to be
checked.

**A broken channel is the shell's death, and the core ends.** §13: without
the shell it is not needed and must not be left hanging. There is
deliberately no separate "sleep mode": a core that outlived its shell is a
process nobody will close.
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
    """The core as a correspondent: parses requests, sends events."""

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

        # The confirmation ledger is taken from the core rather than kept
        # separately: otherwise the permission channel would write out
        # confirmations the executor knows nothing about — and a dangerous
        # action would never go through.
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

        #: Open incoming streams: number -> what is known about it.
        self.incoming: dict[int, dict] = {}
        #: How many bytes we allow to be kept in flight. A small window:
        #: sound arrives continuously, and a large credit means a large delay
        #: between "said" and "heard".
        self.credit_window = 64 * 1024
        self.receiver = None
        #: Recognition and synthesis. Passed in from outside so that they
        #: can be substituted in a check: real models are not installed on
        #: every machine, and the wire has to be checked everywhere.
        self.recogniser = recogniser or speech.recogniser_for(
            getattr(engine, "_settings", None) or {})
        self.synthesiser = synthesiser or speech.synthesiser_for(
            getattr(engine, "_settings", None) or {})
        #: Those passed in from outside are not rebuilt: the check set them deliberately.
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

        #: Where to put received sound if recognition is not needed.
        self.on_audio = None

        # The core's voice goes to the shell, not to a local speaker (4.0-E04).
        engine.voice_out = self._speak
        # The machine is touched by the shell (ADR 0009). The core decides
        # what to do and asks; it has no system calls of its own any more.
        engine.system_out = self.do_system
        # The program index is operating-system data, and it lives in the
        # shell (ADR 0009). The core asks and matches.
        engine.apps_source = self.fetch_apps
        engine.launch_out = self.launch_app
        # Anything dangerous is confirmed with a window, not with words alone (4.0-F11).
        engine.on_question = self._on_question

        #: Our requests awaiting the shell's answer. Until now the server
        #: could only answer; to ask (§11) it has to be able to wait too.
        self._awaiting: dict[str, Callable[[Envelope], None]] = {}

        self._send_lock = threading.Lock()
        self._running = False
        self._on_stop = on_stop
        self.stopped_because = ""
        self._subscribe()

    # -- the core's events ----------------------------------------------------

    def _subscribe(self) -> None:
        """
        Subscribe to every one of the core's events at once.

        Every one, not a hand-written list: the list lives in
        `core/protocol.py`, is checked against the wire's catalogue and
        against the specification, and there must be no second copy of it
        here — that copy would be the first to drift.
        """
        for name in ALL_EVENTS:
            self.engine.bus.on(name, self._make_forwarder(name))

    def _make_forwarder(self, name: str):
        def forward(payload: dict) -> None:
            try:
                self.send(event(name, dict(payload or {}),
                                id=self.ids.next()))
            except ProtocolFault as exc:
                # An event with a wrong payload is a defect of the core.
                # It drops itself but not the session: the correspondent is
                # not to blame for our mistake.
                self._log_broken(name, exc)
            except TransportClosed:
                self.stop("канал закрыт при отправке события")
        return forward

    def _log_broken(self, name: str, exc: Exception) -> None:
        from core.logging_setup import get_logger
        get_logger("wire").error("Событие %s не отправлено: %s", name, exc)

    # -- sending ----------------------------------------------------------------

    def send(self, envelope: Envelope) -> Envelope:
        with self._send_lock:
            self.channels.control.send(encode_frame(envelope))
        return envelope

    # -- receiving --------------------------------------------------------------

    def serve_forever(self) -> str:
        """
        Read the channel while it lives. Returns the reason for stopping.

        A break is not an error but an ordinary end: the shell closed, and
        the core has nothing more to do.
        """
        self._running = True

        # The data channel reads its own stream — that was the whole point
        # of two pipes: a burst of sound must not hold up a command. Started
        # here rather than outside: outside it was started before the
        # running flag went up, and the thread died on the very first check
        # of the condition, in silence.
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
                    continue            # silence, not the end: see Transport.recv
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
        """Handle one message and send everything due in reply."""
        out: list[Envelope] = []

        # An answer to our own request is not a method, and looking for a
        # handler for it would mean answering "unknown method" to our own
        # question.
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

    # -- methods ------------------------------------------------------------------

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
            "commands.builtin": self._commands_builtin,
            "hotkeys.actions": self._hotkey_actions,
            "speech.test": self._speech_test,
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
            "settings.reset": self._settings_reset,
            "stream.open": self._stream_open,
            "stream.close": self._stream_close,
            "stream.credit": self._stream_credit,
        }

    def _hello(self, message: Envelope) -> dict:
        # The data version is taken from the store at the moment of
        # answering: a migration may have happened on load, and a number
        # from a constant would lie.
        store = self._settings()
        if store is not None:
            from core.settings_store import CONFIG_VERSION

            self.session.data_version = int(
                store.get("config_version", CONFIG_VERSION) or CONFIG_VERSION)
        return self.session.handle_hello(message.payload)

    def _shutdown(self, message: Envelope) -> dict:
        self.stop("оболочка попросила завершиться")
        return {"ok": True}

    def _command_handle(self, message: Envelope) -> dict:
        """
        The answer is "accepted", not the result.

        The result will come as an event: a command may think for seconds
        and say several things along the way, and everything but the last
        would be lost.
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
        # The context is copied so that listening events land in the same
        # chain as the request: a new thread starts with an empty context.
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

    # -- settings -----------------------------------------------------------------

    def _settings(self):
        return getattr(self.engine, "_settings", None)

    def _settings_get(self, message: Envelope) -> dict:
        keys = message.payload.get("keys") or []
        store = self._settings()
        schema = settings_schema.describe(keys)
        # What is secret or obsolete does not go out: config_version and
        # first_run are the state of the store, while theme and accent were
        # replaced by finishes (R08). The data is intact, the shell simply
        # no longer needs it.
        return {"values": {k: store.get(k) for k in keys
                           if not schema.get(k, {}).get("secret")
                           and not schema.get(k, {}).get("obsolete")}}

    def _settings_set(self, message: Envelope) -> dict:
        """
        Write the values down and report on each.

        A report per key rather than one "it worked" for the whole parcel:
        of ten values one may not go through, and saying "it was not saved"
        about that is saying nothing. The verdicts are D05 catalogue codes,
        so that the shell branches on them rather than on the text.

        A warning is not a refusal. "The model address is not local" means
        the value was accepted and written down, and the person was told
        what it will lead to: the decision is theirs, not ours.
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
                    # The language is not the sort of setting a program is
                    # restarted for. The replies switch here, the words of
                    # the interface in the shell, each on its own side.
                    from core import i18n
                    i18n.set_language(str(accepted["ui_language"]))
                if "log_level" in accepted:
                    # The journal level could be applied on the fly
                    # (`apply_settings`), but it was called by whoever
                    # changed it — 3.1.0's settings screen. The same loss as
                    # with saving: the screen moved away, the call stayed.
                    from core import logging_setup
                    logging_setup.apply_settings()
                # Write to disk. `set()` only marks the group as changed,
                # and in 3.1.0 the saving was done by whoever changed it —
                # the settings screen. The screen moved to another process
                # and the call stayed there: a setting held until the core
                # finished and then vanished. We write inside the
                # transaction, so that no other thread wedges itself between
                # the change and the write.
                store.save()
        return {"values": {k: store.get(k) for k in accepted},
                "verdicts": verdicts}

    @staticmethod
    def _settle_voice(store, accepted: dict, verdicts: dict) -> None:
        """
        The engine changed — change the voice too, if the old one is foreign
        to it.

        Every engine has its own numbering of voices:
        `ru-RU-SvetlanaNeural` for one and `default` for another. Leaving
        the previous value means leaving a setting that shows "currently
        unavailable" forever and voices nothing; making a person choose a
        voice afresh after every change of engine means demanding a step we
        can take ourselves and will almost always guess right.

        This is said out loud: a setting quietly rewritten is exactly the
        kind of surprise a person later hunts for with their eyes.
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
        The meaning of the values, but **not** their appearance (ADR 0006).

        `layout` is given as `null` explicitly rather than omitted: a
        missing key would read as "not done yet", whereas `null` reads as
        "none of our business" — which is the actual state of affairs.
        """
        keys = message.payload.get("keys") or None
        return {
            "schema": settings_schema.describe(keys),
            "layout": None,
            "note": "раскладку описывает оболочка: ADR 0006",
        }

    def _settings_options(self, message: Envelope) -> dict:
        """
        Which values a key takes right now, on this machine.

        A separate method rather than a field in the schema: the schema
        describes what is always true, and this list changes with a model's
        installation and even with which engine is chosen right now. Keeping
        the changeable next to the constant means one day caching the first
        along with the second.
        """
        store = self._settings()
        keys = message.payload.get("keys") or []
        return {"options": {key: settings_schema.options_for(key, store)
                            for key in keys}}

    # -- reminders --------------------------------------------------------------

    def _reminders(self):
        return getattr(self.engine, "_reminders", None)

    def _reminders_list(self, message: Envelope) -> dict:
        store = self._reminders()
        return {"items": [dict(item) for item in store.active()]}

    def _reminders_create(self, message: Envelope) -> dict:
        """
        Create a reminder from the window.

        By voice this is done by parsing a phrase ("remind me at seven about
        bread"), and at first it seemed the window would manage with the
        same path. It does not: a person at the screen picks a time in a
        field rather than saying it in words, and making the shell compose a
        Russian phrase for the sake of parsing it back means testing the
        parser instead of the intent.

        The time arrives as a stamp rather than as words: the shell has a
        calendar, and its time zone is the same as the core's — they both
        live on one machine.
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

        # The kind affects only what the reminder is called to a person
        # ("Alarm", "Timer", "Reminder"), and the shell is entitled not to
        # know it: an ordinary reminder suits one created from the window.
        kind = str(message.payload.get("kind", "reminder") or "reminder")
        # There is deliberately no event about creation: the list will be
        # requested by whoever created it, and the same one shows it. An
        # event would be needed if reminders were created apart from the
        # shell — but by voice they are created by the same shell over the
        # same connection.
        return {"item": dict(store.add(kind, fire_at, text))}

    def _reminders_cancel(self, message: Envelope) -> dict:
        store = self._reminders()
        if message.payload.get("all"):
            return {"cancelled": int(store.clear_active())}
        item_id = message.payload.get("id")
        return {"cancelled": 1 if store.remove(item_id) else 0}

    # -- the user's own commands ---------------------------------------------------

    def _commands(self):
        return getattr(self.engine, "_cmd_store", None)

    def _commands_list(self, message: Envelope) -> dict:
        return {"items": [dict(c) for c in self._commands().all()]}

    def _speech_test(self, message: Envelope) -> dict:
        """
        Say a test phrase in the current voice.

        A separate method rather than `speech.say`: what is said during a
        check must not land in the conversation history — the person was
        checking the sound, not talking. And the phrase is chosen by the
        core: it is her line, and Rina's words live here (`4.0-F08`).
        """
        self._voice_follows_settings()
        if not self.synthesiser.available():
            return {"ok": False,
                    "reason": str(getattr(self.synthesiser, "last_error", "")
                                  or "синтез недоступен")}

        store = self._settings()
        text = "Проверка связи. Меня слышно и я говорю этим голосом."
        pcm = self.synthesiser.synthesize(
            text,
            voice=str(store.get("voice", "") if store else ""),
            rate=int((store.get("speed", 100) if store else 100) or 100))
        if not pcm:
            return {"ok": False,
                    "reason": str(getattr(self.synthesiser, "last_error", "")
                                  or "синтез ничего не вернул")}

        self.send_speech(pcm, self.synthesiser.sample_rate)
        return {"ok": True, "text": text,
                "seconds": round(len(pcm) / 2 / max(
                    self.synthesiser.sample_rate, 1), 2)}

    def _hotkey_actions(self, message: Envelope) -> dict:
        """
        What a hotkey can be assigned to.

        Given by the core: it is what performs the actions, and it has the
        list. A shell that knew it by heart would offer to assign a hotkey
        to something the core no longer does — and the person would find out
        by pressing the keys.
        """
        from core.i18n import t as tr
        from voice.hotkey_actions import HOTKEY_ACTIONS

        return {"items": [{"value": key, "title": tr(title), "what": tr(what),
                           "icon": icon}
                          for key, (title, what, icon)
                          in HOTKEY_ACTIONS.items()]}

    def _commands_builtin(self, message: Envelope) -> dict:
        """
        What Rina can do with no setting up at all.

        Given by the core, because these are **the phrases people say to
        her** — part of her vocabulary, not interface labels (`4.0-F08`). A
        shell that knew them by heart would show what the core no longer
        understands, and a person would say it aloud for nothing.
        """
        from voice.commands import known_commands

        return {"items": [{"phrase": phrase, "what": what}
                          for phrase, what in known_commands()]}

    def _commands_kinds(self, message: Envelope) -> dict:
        """
        What a command can be made of.

        The names of things come from where the things live (the same rule
        as for `settings.options`): the kinds of command and the system
        actions are enumerated by the core, because it is what performs
        them. A shell that knew this list by heart would drift apart from
        the core in silence — and would show a person an action that no
        longer exists, or hide a new one.

        The same place says which action is **irreversible**: confirmation
        is asked for by the core (§11), but a person must see this in the
        editor already rather than find out at the first firing.
        """
        from core.i18n import t as tr
        from voice import user_commands

        # Translated **on the way out**: the tables in
        # `voice/user_commands.py` are keys, and storing them translated
        # means storing them in one language. Translations have existed in
        # the core since 3.1.0, nobody simply asked for them, and under an
        # English interface the editor said "Программа".
        return {
            "kinds": [{"value": kind, "title": tr(title), "icon": icon}
                      for kind, title, icon in user_commands.COMMAND_TYPES],
            "actions": [{"value": action, "title": tr(title),
                         "destructive": action
                         in user_commands.DESTRUCTIVE_ACTIONS}
                        for action, title in user_commands.SYSTEM_ACTIONS],
            "matches": [{"value": "contains", "title": tr("Фраза встречается")},
                        {"value": "exact", "title": tr("Фраза целиком")}],
        }

    def _commands_save(self, message: Envelope) -> dict:
        """
        Create or change — one method, not two.

        For the shell this is one action: a person edits the card and
        presses "save". Splitting it by whether an identifier already exists
        means making the shell know what the store knows.
        """
        store = self._commands()
        command = dict(message.payload.get("command") or {})
        if command.get("id"):
            store.update(command)
        else:
            # The number is assigned by the core, not by the shell. An
            # identifier that came from outside is somebody else's right to
            # decide which command is which; the same reason the core issues
            # confirmation_id (§11).
            command["id"] = "cmd_" + secrets.token_hex(3)
            store.add(command)
        return {"command": dict(command)}

    def _commands_delete(self, message: Envelope) -> dict:
        # The store does not say whether it deleted anything, so we count
        # ourselves: "deleted" and "there was no such thing" are different
        # answers for the shell.
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
        Hand over the commands rather than write a file.

        The shell picks the file and writes it: the save dialogue is its
        work, and the core cannot do it anyway. The core hands over the
        content.
        """
        from core import data_transfer

        store = self._commands()
        # Статистика запусков едет вместе с командами: она про них и без
        # них бессмысленна. Лежит она в настройках, а не в хранилище команд,
        # поэтому берётся отсюда.
        stats = self._settings().get("command_stats", {}) or {}
        return data_transfer.commands_payload(
            [dict(c) for c in store.all()], stats)

    def _commands_import(self, message: Envelope) -> dict:
        """
        Accept a commands file. The shell read it; the judgement is here.

        **Everything imported arrives switched off.** A command is the
        launching of a program, and this file could have been written by
        anyone; switching on is a deliberate step taken after looking at
        what exactly was added.

        **A duplicate is the same set of phrases, not the same number.** A
        file from another machine carries identifiers of its own, while the
        phrases are what the command is to a person. Matching by identifier
        let a file imported twice arrive twice — it was written by 4.0 with
        fresh numbers each time.

        Both rules came back from 3.1.0 along with `core/data_transfer.py`:
        the 4.0 path had quietly grown its own, shorter, set.
        """
        from core import data_transfer
        from core.wire.errors import fault

        payload = message.payload
        # `file` is what the shell read; the older shape is still taken —
        # the file may have been made by hand.
        data = payload.get("file")
        if data is None:
            data = payload.get("commands")
        try:
            incoming = data_transfer.commands_from_data(data, source="оболочка")
        except data_transfer.TransferError as problem:
            raise fault(problem.code, str(problem))

        store = self._commands()
        merged, added, skipped = data_transfer.merge_commands(
            [dict(c) for c in store.all()], incoming,
            lambda: "cmd_" + secrets.token_hex(3))
        store.save_all(merged)
        return {"added": added, "skipped": skipped}

    # -- the conversation's history ------------------------------------------------

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
        """Содержимое файла истории — в том же конверте, что и команды."""
        from core import data_transfer

        return data_transfer.history_payload(
            [dict(i) for i in self._history().all()])

    # -- plugins ---------------------------------------------------------------------

    def _plugin_manager(self):
        return getattr(self.engine, "_plugins", None)

    @staticmethod
    def _plugin_state(plugin_id: str, loaded) -> dict:
        """
        What the shell knows about a plugin.

        A broken plugin is shown together with the reason rather than
        disappearing from the list: a person installed it themselves and
        must see why it does not work. A plugin that vanished looks like "I
        never installed it".
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
            # What to call the plugin's section in the shell's column (`4.0-F04`).
            "page_title": str(getattr(loaded, "page_title", "")
                              or manifest.name),
            "page_icon": str(getattr(loaded, "page_icon", "")
                             or manifest.icon),
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
        Switch a plugin on or off.

        What is returned is the **state after** the change, not "accepted":
        a plugin may refuse to load, and then "on" would be an untruth. The
        shell draws what is, not what was asked for.
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
        The declarative description of a plugin's page.

        A plugin describes the page as a list of elements, and the shell
        draws them. This was decided back in 3.1.0
        (`plugins/page_spec.py`), when a plugin stopped returning a
        ready-made widget — and that is exactly why a plugin's page is drawn
        in another process in another language without a single change to
        the plugin itself.
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
        A button on a plugin's page was pressed; the answer is a new page.

        The new description is returned in the same answer rather than as an
        event: a button changes what is drawn next to it, and making the
        shell ask for the page a second time would mean showing it stale by
        exactly one round.
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
        Install a plugin from a folder or an archive.

        The contents are checked before copying (`plugins/manager.py`): the
        manifest and `main.py` are required, or the catalogue will gain
        rubbish that will show up as a broken plugin on every start.

        **The core installs, and the shell shows the picker.** The path
        arrives already chosen: a file dialogue is interface, while
        unpacking and checking are work with data.
        """
        from plugins.manager import PluginInstallError, install_plugin

        source = str(message.payload.get("source", "")).strip()
        if not source:
            raise fault("protocol.invalid_payload", "Нечего устанавливать.")

        try:
            # A pair is returned: the name and whether there was a plugin
            # under that name. Replacement and installation are different
            # answers to a person, and the second value here is no
            # formality: a replaced plugin is forcibly switched off, so that
            # a slipped-in archive with somebody else's name does not run by
            # itself.
            plugin_id, replaced = install_plugin(source)
        except PluginInstallError as exc:
            raise fault("plugin.not_found", str(exc)) from exc
        except Exception as exc:                     # noqa: BLE001
            raise fault("internal", str(exc)) from exc

        # The list is rebuilt at once: an installed plugin must appear in
        # the window without a restart.
        manager = self._plugin_manager()
        if manager is not None:
            try:
                manager.discover()
            except Exception:                        # noqa: BLE001
                log.exception("Плагины не пересобрались после установки")

        return {"plugin_id": plugin_id, "replaced": bool(replaced)}

    def _settings_reset(self, message: Envelope) -> dict:
        """
        Reset the settings to their defaults.

        **Only the settings group** is reset: commands, history and plugins
        stay. Deleting those is a separate deliberate action rather than a
        side effect of "put it back as it was"; this rule came from 3.1.0
        along with the store itself.
        """
        store = self._settings()
        if store is None:
            raise fault("internal", "Хранилище недоступно.")

        from core.logging_setup import security_log

        store.reset(groups=("settings",))
        # Into the security journal: a settings reset erases privacy too —
        # text recording switched off, the chosen language, the window's
        # permissions.
        security_log().warning("Настройки сброшены к умолчаниям")
        return {"ok": True,
                "values": {k: store.get(k) for k in settings_schema.SETTABLE}}

    # -- tasks ----------------------------------------------------------------------

    def _task_cancel(self, message: Envelope) -> dict:
        return self.tasks.cancel(str(message.payload.get("task_id", "")))

    # -- data streams (4.0-D07, D08; the core's side for 4.0-F09) ------------------

    def _stream_open(self, message: Envelope) -> dict:
        """
        Open a binary stream and issue the first credit right away.

        The initial credit is zero (§8), and until the receiver issues it
        the sender stays silent. We issue it here and now: the core is ready
        to receive from the very moment it agreed to open the stream, and
        there is no point making the shell wait for a separate message.
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
        """Credit from the shell — for streams the core sends (4.0-F10)."""
        stream_id = message.payload.get("stream_id")
        extra = int(message.payload.get("bytes") or 0)
        if stream_id in self.data.open and extra > 0:
            self.data.grant(stream_id, extra)
        return {"accepted": True}

    def pump_data(self) -> str:
        """
        Read the data channel while it lives.

        A separate thread, because the channel is separate — that was the
        whole point of two pipes: a burst of sound must not hold up a
        command. Credit is issued **as data is handled**, not as it is
        received: credit for what lies unread in the buffer is the very
        unbounded queue the scheme exists to do away with.
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
            # A stream nobody agreed on. Not a break: the sender may not
            # have had time to learn that we closed it.
            return
        state["bytes"] += len(frame.payload)
        state["frames"] += 1
        if state["kind"] == "audio.input":
            if self.on_audio is not None:
                self.on_audio(frame.stream_id, frame.payload, state["format"])
            self._hear(frame.payload)
        # Handled — so we return credit for what was handled.
        self.send(Envelope.event("stream.credit",
                                 {"bytes": len(frame.payload)},
                                 id=self.ids.next(),
                                 stream_id=frame.stream_id))

    # -- a question to the person (4.0-F11, §11) -----------------------------------

    def ask_shell(self, method: str, payload: dict,
                  on_answer: Callable[[Envelope], None]) -> Envelope:
        """Ask the shell a question and remember who is waiting for the answer."""
        request = Envelope.request(method, payload, id=self.ids.next())
        self._awaiting[request.id] = on_answer
        return self.send(request)

    def ask_shell_sync(self, method: str, payload: dict,
                       timeout: float = 10.0) -> dict:
        """
        Ask the shell and wait for the answer.

        Needed because a system action is performed **inside** the parsing
        of a command: the tool "turn the volume up" is obliged to return an
        outcome rather than "I asked". The asynchronous `ask_shell` will not
        do for this — it leaves the caller without an answer.

        We wait in the thread that is handling the command, not in the
        receiving one: the receiving thread is what answers here, and
        blocking it would mean waiting for the answer with the very thread
        that will bring it.
        """
        done = threading.Event()
        got: dict = {}

        def answered(reply: Envelope) -> None:
            got["reply"] = reply
            done.set()

        # A check on our own side: a shell without Windows will not declare
        # `system`, and it is better to learn of that here than from
        # silence.
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
        Ask the shell for the index of installed programs.

        Matching a name to a record stays here: "телеграм" → Telegram is
        transliteration and fuzzy matching, that is, language, and language
        is the core's business. The shell hands over facts about the system,
        the core decides what the person meant (ADR 0009).
        """
        try:
            answer = self.ask_shell_sync("apps.index", {"refresh": refresh},
                                         timeout=60.0)
        except ProtocolFault:
            # A shell without an index is no reason to fall over: the
            # command "open telegram" will answer "not found", and the rest
            # will work.
            return []
        return list(answer.get("entries") or [])

    def launch_app(self, launch: str, kind: str = "file") -> tuple[bool, str]:
        """Ask the shell to launch what was found."""
        try:
            answer = self.ask_shell_sync("apps.launch",
                                         {"launch": launch, "kind": kind},
                                         timeout=30.0)
        except ProtocolFault as exc:
            return False, str(exc)
        return bool(answer.get("ok")), str(answer.get("reason", ""))

    def do_system(self, action: str) -> tuple[bool, str]:
        """
        Ask the shell to perform a system action.

        The words stay here: "Volume turned up" is Rina's line (ADR 0007),
        and the shell answers with a fact. So what goes out is a pair
        "it worked, the detail" rather than a ready-made sentence.
        """
        try:
            answer = self.ask_shell_sync("system.do", {"action": action})
        except ProtocolFault as exc:
            return False, str(exc)
        return bool(answer.get("ok")), str(answer.get("detail", ""))

    def _on_question(self, question) -> None:
        """
        The core asked a question — show it to the person in a window (§11).

        **Only the irreversible** is asked about: a clarifying "which of the
        three telegrams" has neither danger nor a preview, and tearing it
        out into a modal window would mean interrupting the conversation for
        a choice that is easier made in words.

        The voice path is not thereby cancelled: a person can answer "yes"
        out loud and the question closes itself — the window then simply
        stops being needed.
        """
        if question.kind not in ("confirm_action", "confirm_command"):
            return
        if not self.session.ready:
            return
        if "permissions" not in self.session.peer_capabilities:
            return          # the shell cannot ask: it stays a voice question

        asked = question.to_dict()
        action = asked.get("action") or ""
        command_id = asked.get("command_id") or ""

        # The preview is what a person is shown instead of the action's
        # name. §11 demands showing **what exactly will happen**: "Shut down
        # the computer?" is something a person has time to take in, while
        # "power_action" means nothing.
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
        The shell's answer. Refusal by default: everything but an explicit
        "yes" is a "no".
        """
        granted = (message.type == "response"
                   and message.payload.get("granted") is True)
        self.engine.answer_question(granted)

    # -- speech (4.0-E03, E04) --------------------------------------------------------

    def _hear(self, pcm: bytes) -> None:
        """
        Accumulate sound and recognise a finished phrase.

        Slicing into phrases is done here, not in the shell: only next to
        recognition is it known how much silence counts as a pause inside a
        sentence and how much as the end of a phrase.

        Recognition runs in a thread of its own: the model thinks for
        hundreds of milliseconds, and the data channel is read on this same
        thread — the delay would turn into missed sound.
        """
        for phrase in self.segmenter.feed(pcm):
            threading.Thread(target=self._recognise, args=(phrase,),
                             name="rina-stt", daemon=True).start()

    def _recognise(self, phrase: bytes) -> None:
        with trace_scope():
            if not self.recogniser.available():
                # Silence will not do here: the person will decide they
                # cannot be heard and start speaking louder.
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
                return          # silence is neither an error nor worth reporting
            self.engine.bus.emit("speech.recognized", text=heard.text)
            self.engine.handle_command_async(heard.text, source="voice")

    def _voice_follows_settings(self) -> None:
        """
        Rebuild synthesis and recognition if the engine was changed.

        Otherwise the choice in settings began to take effect only after the
        core restarted: a person picks Edge, hears silence and decides
        something is broken. A setting that "will apply some day" is not a
        setting but a promise; the ones marked `restart_required` say so
        honestly, and these two promised nothing of the kind.
        """
        store = self._settings()
        if store is None:
            return
        # What is compared is what was asked for, not what came of it: an
        # engine the core cannot do gives "off", and comparing by name would
        # rebuild it on every line.
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
        Synthesise and send to the shell.

        Synthesis in the core, playback in the shell: the models live where
        the ML ecosystem is, and the sound where latency is low and audio is
        native.
        """
        self._voice_follows_settings()
        if not self.synthesiser.available():
            return          # the text already went as an event; there is simply no voice
        pcm = self.synthesiser.synthesize(
            text,
            voice=str(self._settings().get("voice", "") if self._settings()
                      else ""),
            rate=int((self._settings() or {}).get("speed", 100) or 100))
        if not pcm:
            return
        self.send_speech(pcm, self.synthesiser.sample_rate)

    def send_speech(self, pcm: bytes, sample_rate: int) -> None:
        """Send ready-made sound to the shell in chunks over the data channel."""
        if self.channels.data is None:
            return

        # The rate is declared when the stream is opened, so a change of
        # engine is a new stream rather than a continuation of the old one.
        # Otherwise speech at 24000 would go into a stream declared at
        # 22050, and Rina would speak lower and slower than she should.
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
            # The shell will issue credit, but waiting for it in silence is
            # dishonest as regards time: the first chunk of speech must go
            # out at once. We give ourselves credit for one reply and after
            # that live by what is issued.
            self.data.grant(self._speech_stream, 512 * 1024)

        chunk = 8192
        for offset in range(0, len(pcm), chunk):
            piece = pcm[offset:offset + chunk]
            if self.data.available(self._speech_stream) < len(piece):
                break       # the shell cannot keep up: cutting speech off is
                            # more honest than piling it up in memory
            self.channels.data.send(self.data.send(self._speech_stream, piece))

    # -- the break ---------------------------------------------------------------

    def on_disconnect(self) -> dict[str, int]:
        """
        The shell has gone: reset everything volatile (§13).

        The core ends after this — see the module header.
        """
        return self.volatile.reset()
