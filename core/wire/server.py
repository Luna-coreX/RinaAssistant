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

import collections
import contextvars
import queue
import secrets
import threading
import time
from typing import Any, Callable

from core import settings_schema, speech
from core.logging_setup import get_logger, safe
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
from core.i18n import t as tr
from core.trace import trace_scope
from core.wire.transport import Channels, TransportClosed


log = get_logger("wire")


#: The settings that decide **what gets built** for voice — as against
#: those read at every use (`voice`, `speed`). A change to any of them
#: makes the current recogniser or synthesiser stale; a change to anything
#: else does not. See `ProtocolServer._voice_follows_settings`.
_VOICE_KEYS = ("stt_engine", "vosk_model", "whisper_model",
               "tts_engine", "piper_model")


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
        self._speech_wanted = tuple(
            str((store.get(key, "") if store else "") or "")
            for key in _VOICE_KEYS)
        self.segmenter = speech.Segmenter()
        self._speech_stream = 0
        #: Downloads in flight, by model id — so they can be
        #: cancelled, and so the same one is not started twice.
        self._fetching: dict = {}
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
        # A setting the engine writes itself — accepting an offer, or
        # switching the listening mode — takes a different road from
        # `settings.set`, and the voice is rebuilt on that road only.
        engine.settings_changed = self._voice_follows_settings
        # A new command silences the answer to the previous one.
        engine.hush_out = self.hush
        engine.launch_out = self.launch_app
        # What is going on outside the command (`4.0b-A09`): which program
        # is in front, whether one is running. The shell has the machine
        # (ADR 0009); the core asks when a condition needs it and keeps
        # nothing (`T-19`).
        engine.machine_out = self.ask_machine
        # Anything dangerous is confirmed with a window, not with words alone (4.0-F11).
        engine.on_question = self._on_question

        #: Our requests awaiting the shell's answer. Until now the server
        #: could only answer; to ask (§11) it has to be able to wait too.
        self._awaiting: dict[str, Callable[[Envelope], None]] = {}

        #: What to do once the answer is on the wire — not a moment before.
        #:
        #: There is exactly one thing so far and it is worth the mechanism.
        #: The listening mode is restored from the settings while `hello`
        #: is being answered, and restoring it announces itself with an
        #: event. Sent from inside the handler, that event leaves **before**
        #: the reply — and until the reply arrives the other side has no
        #: agreed protocol version, so it is not listening for events yet
        #: and cannot be blamed for missing one. The setting said "always
        #: listening", the core believed it, the shell never heard, and the
        #: microphone stayed shut: the switch showed a mode that was not
        #: running.
        #:
        #: Anything a handler wants to do after its own answer goes here
        #: rather than on a timer. A delay chosen by hand is a race whose
        #: losing side is somebody else's slow machine.
        self._after_reply: list[Callable[[], None]] = []

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

            # And only now — see `_after_reply`. One that throws loses
            # itself and nothing else: the answer has already gone, and
            # taking the session down after answering would be worse than
            # the thing that failed.
            while self._after_reply:
                todo = self._after_reply.pop(0)
                try:
                    todo()
                except Exception as exc:                # noqa: BLE001
                    self._log_broken("после ответа", exc)
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
            "sessions.list": self._sessions_list,
            "sessions.finish": self._sessions_finish,
            "todo.list": self._todo_list,
            "todo.add": self._todo_add,
            "todo.close": self._todo_close,
            "todo.remove": self._todo_remove,
            "reminders.list": self._reminders_list,
            "reminders.cancel": self._reminders_cancel,
            "system.foreground": self._foreground,
            "reminders.create": self._reminders_create,
            "commands.list": self._commands_list,
            "commands.kinds": self._commands_kinds,
            "commands.builtin": self._commands_builtin,
            "hotkeys.actions": self._hotkey_actions,
            "setup.state": self._setup_state,
            "setup.finish": self._setup_finish,
            "models.catalogue": self._models_catalogue,
            "models.fetch": self._models_fetch,
            "speech.test": self._speech_test,
            "commands.save": self._commands_save,
            "commands.try": self._commands_try,
            "commands.delete": self._commands_delete,
            "commands.set_enabled": self._commands_set_enabled,
            "commands.export": self._commands_export,
            "commands.import": self._commands_import,
            "privacy.inventory": self._privacy_inventory,
            "privacy.forget": self._privacy_forget,
            "privacy.export": self._privacy_export,
            "history.list": self._history_list,
            "history.clear": self._history_clear,
            "history.export": self._history_export,
            "task.cancel": self._task_cancel,
            "plugins.list": self._plugins_list,
            "plugins.set_enabled": self._plugins_set_enabled,
            "plugins.page": self._plugins_page,
            "plugins.home": self._plugins_home,
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
        answer = self.session.handle_hello(message.payload)

        # Ears outside is a property of the handshake, not of an open
        # stream. The shell opens the microphone stream **in answer to** the
        # core announcing that it listens, so at the first announcement
        # there is none: learning it from the stream would send the first
        # listen to the core's own microphone — the very path being removed
        # here.
        self.engine.ears_outside = (
            "audio.input" in self.session.peer_capabilities)

        # And the listening mode is restored here rather than at start-up:
        # it needs to know whether the ears are outside, and that is settled
        # by this very handshake. Restored at all because a setting saying
        # "always listening" while nothing listens is the same lie as the
        # switch that showed "off" while it was on — merely the other way
        # round.
        #
        # **After the answer, not inside it** (see `_after_reply`). Done
        # here, the event that announces the mode overtook the reply it was
        # meant to follow, and the shell — which has no session until the
        # reply arrives — dropped it. Four days of "always listening" being
        # on in the settings and off in fact.
        store = self._settings()
        if store is not None and bool(store.get("always_listen", False)):
            self._after_reply.append(
                lambda: self.engine.set_always_listen(True))

        return answer

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

    # -- the setup wizard (4.0b-A14) ----------------------------------------

    def _setup_state(self, message: Envelope) -> dict:
        """
        Is this a first run.

        Its own method rather than a settings key read out. `first_run` is
        marked secret — it is the state of the store, not something a person
        edits — and `settings.get` is right to withhold it. "Has this person
        been set up yet" is a question about the session, and it gets its own
        door rather than a hole cut in someone else's.
        """
        store = self._settings()
        return {"needed": bool(store.get("first_run", True)) if store
                else False}

    def _setup_finish(self, message: Envelope) -> dict:
        """The wizard is done: do not show it again."""
        store = self._settings()
        if store is not None:
            store.set("first_run", False)
            store.save()
        return {"done": True}

    def _models_catalogue(self, message: Envelope) -> dict:
        from core import models

        return {"items": models.catalogue(self._settings(),
                                          running=self._fetching)}

    def _models_fetch(self, message: Envelope) -> dict:
        """
        Start downloading the named models, as ordinary long tasks.

        **No events of its own, and that is the specification's decision
        rather than an omission** (§10). Progress goes as `task.progress`
        and stopping as `task.cancel`, because a download is the same kind
        of lasting work as a model thinking or an archive being unpacked.
        Three `model.*` events were written once and removed before first
        use: they said the same thing a second way, and two ways to say one
        thing is exactly the case where one of them is later forgotten.

        I wrote them a second time anyway, and the check for §6 caught it.

        Returns at once: a download is minutes, and a call that waited for
        one would hold the control channel for all of them.
        """
        from core import models

        wanted = [str(i) for i in (message.payload.get("ids") or [])]
        started = []
        for wanted_id in wanted:
            if wanted_id in self._fetching:
                continue

            # A package, and its **name comes from `PACKAGES`**, never from
            # this message (`T-20`). The shell names an identifier; an
            # unknown one is skipped in silence. Were the pip name taken
            # from the payload, "install this for me" would be "run this on
            # my machine" for anyone who can send us a message.
            package = models.find_package(wanted_id)
            if package is not None:
                started.append(self._work_as_task(
                    wanted_id, package.title,
                    models.Install(package,
                                   settings=self._settings())))
                continue

            model = models.find(wanted_id)
            # What the engine fetches for itself is skipped rather than
            # reported as started: we do not drive that transfer, and saying
            # we did would leave the shell waiting for progress that is
            # never coming, with a cancel button that cancels nothing.
            if model is None or not model.ours:
                continue
            started.append(self._work_as_task(
                wanted_id, model.title,
                models.Fetch(model, settings=self._settings())))
        return {"tasks": started}

    def _work_as_task(self, what_id: str, title: str, work) -> dict:
        """
        One download or installation, wrapped in the task lifecycle.

        One method for both, because from outside they are the same thing: a
        long piece of work that reports where it is and can be stopped. They
        differ only in whether there is a share to draw, and that difference
        is carried by the numbers rather than by a second code path.
        """
        task = self.tasks.create()
        task.start()
        began = time.monotonic()

        def told(state: dict) -> None:
            # Cancellation is noticed rather than pushed, because that is
            # the contract `Task` states: "it is obliged to stop itself, on
            # noticing the flag".
            if task.cancel_requested:
                work.cancel()

            name = state.get("state")
            if name == "downloading":
                total = state.get("total") or 0
                done = state.get("done") or 0
                # A share only where there is one. `pip` speaks in lines,
                # not bytes; a bar invented from a line count would mean
                # nothing and move convincingly.
                self.send(task.progress(
                    state.get("note") or tr(
                        "Скачиваю {name}: {done} из {total} МБ",
                        name=title,
                        done=done // (1024 * 1024),
                        total=total // (1024 * 1024)),
                    fraction=(done / total) if total else None))
            elif name == "unpacking":
                self.send(task.progress(tr("Распаковываю {name}",
                                           name=title)))
            elif name in ("ready", "cancelled", "failed"):
                self._fetching.pop(what_id, None)
                if name == "ready":
                    self.send(task.done({"id": what_id}))
                    self._tell_it_finished(what_id, title,
                                           time.monotonic() - began)
                elif name == "cancelled":
                    self.send(task.cancelled())
                else:
                    self.send(task.failed(state.get("error", "")))

        work.on_progress = told
        # The task's number is remembered on the work itself, so that a
        # window opened later can be told which task to cancel.
        work.task_id = task.id
        self._fetching[what_id] = work
        work.start()
        return {"id": what_id, "task_id": task.id}

    #: Below this a finished job is not news. A download of two seconds
    #: needs no announcement; one of two minutes does, because by then
    #: the person has gone off to do something else and the window that
    #: was showing the bar may not even be open.
    TELL_AFTER = 10.0

    def _tell_it_finished(self, what_id: str, title: str,
                          seconds: float) -> None:
        """
        Say that a long job is done — and offer what has become possible.

        `4.0b-E06`, the two halves that belong together. An event on the
        wire is not a report: it draws a bar in a window nobody is
        necessarily looking at. A person who started a two-hundred-
        megabyte download and walked away learns it finished by going
        back and checking, which is the opposite of being told.

        And the offer. Downloading a voice leaves `piper_model` pointing
        at it and `tts_engine` still `silent` — that is, the person waits
        out sixty megabytes and Rina goes on answering in text. What is
        offered is only ever the thing that would otherwise do nothing:
        if an engine of that kind is already chosen, the choice was
        somebody's and is not ours to second-guess.
        """
        if seconds < self.TELL_AFTER:
            return
        from core import models

        store = self._settings()
        model = models.find(what_id)
        offer = self._worth_offering(model, store) if store else None
        if offer is None:
            self.engine.say(tr("{name} — готово.", name=title))
            return
        key, value = offer
        self.engine.offer(
            key, value, title,
            tr("{name} — готово. Включить?", name=title))

    @staticmethod
    def _worth_offering(model, store):
        """Which setting the finished download makes possible, if any."""
        if model is None or not getattr(model, "engine", ""):
            return None
        key = "tts_engine" if model.purpose == "tts" else "stt_engine"
        off = ("", "silent") if model.purpose == "tts" else ("", "disabled")
        if str(store.get(key, "") or "") not in off:
            return None            # already chosen, and not by us
        return key, model.engine

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
                # **The settings that change what the program may do.**
                # Only the reset to defaults was recorded, so switching
                # the model to somebody else's server, letting the
                # journal keep the texts of replies, or pointing the
                # program at a new folder to launch things from left no
                # trace at all — and those are the changes one goes back
                # to the journal about. The name and the new value: these
                # are settings, not speech, and a value one cannot see is
                # a line that answers nothing.
                watched = sorted(set(accepted) & settings_schema.WATCHED)
                if watched:
                    from core.logging_setup import security_log
                    for key in watched:
                        security_log().info("Настройка %s → %r",
                                            key, accepted[key])
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

            # A setting whose meaning is a mode that is running right now.
            # Written here and applied nowhere, it moved the switch and
            # changed nothing: the hotkey for "always listening" goes
            # through `settings.set`, so pressing it stored a flag and the
            # microphone stayed exactly as it was until the next start.
            # The same lie as `4.0b-V02` through another door — the setting
            # says one thing, the program does another — and the two doors
            # together are how the flag came to say "on" while the mode had
            # never run at all.
            #
            # Outside the transaction: the engine writes the setting down
            # itself and saves, and it must not do that with the store's
            # own write still open. It costs nothing when the mode is
            # already in that state — it returns at the first line.
            # A choice of engine or model is a choice that must take
            # effect now. It was applied from two places only — the
            # "test the voice" button and the moment of speaking — so
            # recognition, which neither of them touches, went on using
            # whatever had been built at startup. A person picking Vosk
            # and a model was told, in reply to the next thing they
            # said, "recognition is unavailable: choose a model in
            # settings" — advice to do what they had just done. It came
            # right after a restart, which is what made it read as "the
            # first launch is broken".
            #
            # After the answer, like the mode below: rebuilding loads a
            # model, and a caller waiting on `settings.set` should not
            # wait out a model load to learn their value was saved.
            if accepted.keys() & set(_VOICE_KEYS):
                self._after_reply.append(self._voice_follows_settings)

            if "always_listen" in accepted:
                # After the answer, like the restore at the handshake and
                # for the same reason: applying it announces the mode, and
                # an announcement that overtakes the reply it belongs to
                # arrives before the caller knows its own call succeeded.
                wanted = bool(accepted["always_listen"])
                self._after_reply.append(
                    lambda: self.engine.set_always_listen(wanted))
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

    # -- working sessions (4.0b-A02) ---------------------------------------

    def _sessions_list(self, message: Envelope) -> dict:
        """
        Every session, the open one included and marked as such.

        Closed ones come too: "what did I do yesterday" is the question
        the whole thing exists for, and a core that returned only what
        is running now would leave no way to answer it. Whoever shows
        them sorts and filters.
        """
        store = self.engine.sessions
        items = []
        for one in store.all():
            items.append({**one, "spent": store.spent(one)})
        return {"items": items}

    def _sessions_finish(self, message: Envelope) -> dict:
        """
        Close the open session from the window.

        The same act as saying it aloud, and it goes through the same
        store: a second way of closing that wrote the field itself
        would be a second place to forget the focus flag.
        """
        session = self.engine.sessions.finish(
            str(message.payload.get("note", "")))
        if session is None:
            raise fault(ERROR_INVALID_PAYLOAD, "открытой сессии нет")
        return {"item": {**session,
                         "spent": self.engine.sessions.spent(session)}}

    # -- things to do (4.0b-A13) --------------------------------------------

    def _todo_list(self, message: Envelope) -> dict:
        """
        The whole list, closed ones included.

        The closed ones are handed over too, and whoever shows them may
        filter: "what did I get done today" is a fair question, and a core
        that returns only the open ones leaves no way to answer it.
        """
        return {"items": self.engine.todo.all()}

    def _todo_add(self, message: Envelope) -> dict:
        item = self.engine.todo.add(str(message.payload.get("text", "")))
        if item is None:
            raise fault(ERROR_INVALID_PAYLOAD, "дело без текста")
        return {"item": item}

    def _todo_close(self, message: Envelope) -> dict:
        todo_id = str(message.payload.get("todo_id", ""))
        done = bool(message.payload.get("done", True))
        store = self.engine.todo
        changed = store.close(todo_id) if done else store.reopen(todo_id)
        return {"changed": changed}

    def _todo_remove(self, message: Envelope) -> dict:
        return {"removed": self.engine.todo.remove(
            str(message.payload.get("todo_id", "")))}

    def _reminders_list(self, message: Envelope) -> dict:
        store = self._reminders()
        return {"items": [dict(item) for item in store.active()]}

    def _foreground(self, message: Envelope) -> dict:
        """
        The shell reports: the person switched to this program
        (`4.0b-A03`).

        **Only the shell sends this, and only while the watch is on.** The
        core checks the setting at its own end all the same: time passes
        between the person switching it off and the shell noticing, and in
        that gap the core is obliged to keep quiet by itself.

        The answer is how many reminders fired, and zero is the ordinary
        case. The shell does nothing with that number; it exists because
        "accepted" with no distinguishable outcome cannot be checked.
        """
        if not self._settings().get("watch_apps", False):
            return {"fired": 0, "watching": False}
        launch = str(message.payload.get("launch") or "")
        return {"fired": self.engine.note_foreground(launch),
                "watching": True}

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
            # `step_only` says which kinds are steps of a sequence rather
            # than commands in their own right (`4.0b-A09`). That is a
            # statement about meaning, so it comes from here; where to put
            # such a kind in the window is the shell's business.
            "kinds": [{"value": kind, "title": tr(title), "icon": icon,
                       "step_only": kind in user_commands.STEP_ONLY}
                      for kind, title, icon in user_commands.COMMAND_TYPES],
            "conditions": [{"value": name, "title": tr(title)}
                           for name, title in user_commands.CONDITIONS],
            "limits": {"repeat": user_commands.MAX_REPEAT,
                       "depth": user_commands.MAX_DEPTH},
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

    def _commands_try(self, message: Envelope) -> dict:
        """
        Try a card that has not been saved (`4.0b-A09`).

        The editor could assemble a command and could save it, and until it
        was saved there was no way to find out whether it did what was
        meant. Saving in order to find out leaves a command behind on every
        attempt, and a person trying a phrase four times ends up with four
        commands to delete.

        Nothing is stored: no identifier is issued, the run counter is not
        bumped, and the card goes straight to the tool — which narrows it
        through the same function the import path uses.
        """
        card = message.payload.get("command")
        if not isinstance(card, dict):
            return {"accepted": False}
        self.engine.try_command(dict(card))
        return {"accepted": True}

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
        # The run statistics travel together with the commands: they are
        # about them and mean nothing without them. They live in the
        # settings rather than in the command store, which is why they are
        # taken from here.
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

        # Merging and writing in one call: a transaction's boundaries must
        # coincide with the boundaries of read-modify-write, and the caller
        # should not have to remember that.
        added, skipped = self._commands().merge(
            incoming, lambda: "cmd_" + secrets.token_hex(3))
        return {"added": added, "skipped": skipped}

    # -- the conversation's history ------------------------------------------------

    def _history(self):
        return getattr(self.engine, "_history", None)

    def _privacy_inventory(self, message: Envelope) -> dict:
        """
        Everything kept about a person, group by group (`4.0b-B01`).

        Assembled by walking the store, not from a list somebody maintains:
        a kind of personal data added later has to appear here without
        anybody remembering to add it. See `core/privacy.py`.

        **Groups arrive unnamed.** The core says what it keeps; what a group
        is called belongs to the shell (ADR 0006, `4.0-F08`). The shell is
        obliged to show a group it does not recognise, under its own
        identifier — a privacy page that quietly drops a category is worse
        than no page at all.
        """
        from core import privacy

        settings = self._settings()
        if settings is None:
            return {"groups": [], "gathered_at": privacy.gathered_at()}
        return {
            "groups": privacy.inventory(settings),
            "gathered_at": privacy.gathered_at(),
        }

    def _privacy_forget(self, message: Envelope) -> dict:
        """
        Forget what is kept about a person (`4.0b-B02`).

        Three shapes, and the difference between them is the payload rather
        than three methods: `ids` — these entries; a `group` alone — that
        group entire; `everything` — all of it.

        Answers with **how many** went. "Done" and "there was nothing
        there" are different answers, and a page that says "forgotten" over
        an entry still on the screen teaches a person to distrust the
        button they came here to trust.
        """
        from core import privacy

        settings = self._settings()
        if settings is None:
            return {"forgotten": 0}

        if message.payload.get("everything"):
            return {"forgotten": privacy.forget_everything(settings)}

        group = str(message.payload.get("group") or "")
        if not group:
            return {"forgotten": 0}

        ids = message.payload.get("ids")
        if ids is not None and not isinstance(ids, list):
            return {"forgotten": 0}
        return {"forgotten": privacy.forget(settings, group, ids)}

    def _privacy_export(self, message: Envelope) -> dict:
        """
        Everything kept about a person, as the contents of a file
        (`4.0b-B03`).

        The core hands over the contents; the shell picks the place and
        writes it (§6, ADR 0009). Same division as the commands export, and
        the same envelope, so a file can be told from another kind of file
        by its first line.
        """
        from core import privacy

        settings = self._settings()
        if settings is None:
            return {}
        return privacy.export(settings)

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
        """The contents of a history file — in the same envelope as the
        commands."""
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

    def _plugins_home(self, message: Envelope) -> dict:
        """
        What switched-on plugins want to show on the home screen.

        Everything at once rather than plugin by plugin: the home screen
        draws them together, and asking one at a time would make it appear
        in pieces.
        """
        manager = self._plugin_manager()
        if manager is None:
            return {"tiles": []}
        return {"tiles": manager.home_tiles()}

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
        # The grant travels as `stream.credit`, the same road every later
        # one takes (§8: the initial credit is zero and the sender is
        # silent until the first one arrives). The number in the answer
        # below only **reports** it — adding both would give the sender
        # twice the window and quietly undo the backpressure. The shell
        # once did exactly that, and the two roads hid a break in the one
        # that mattered.
        self.send(Envelope.event("stream.credit", {"bytes": granted},
                                 id=self.ids.next(), stream_id=stream_id))
        return {"accepted": True, "credit": granted}

    def _stream_close(self, message: Envelope) -> dict:
        """
        Close the stream — and hear out what was left half-said.

        **The last phrase used to wait for the next one.** A phrase is cut
        out by the silence that follows it, and when the microphone shuts
        at that very moment no silence ever comes: the words stay in the
        segmenter's buffer. They then surfaced during the **next** listen,
        so Rina answered the previous phrase almost before the person had
        started the new one — "she answers instantly and does not let me
        finish". The journal showed it plainly: two phrases heard, one line
        of recognised text.

        The end of the stream is the end of the phrase. Nothing more is
        coming, and there is nothing to wait for.
        """
        stream_id = message.payload.get("stream_id")
        state = self.incoming.pop(stream_id, None)
        if state is not None and state.get("kind") == "audio.input":
            tail = self.segmenter.flush()
            if tail:
                self.heard["phrases"] += 1
                log.info("Договорено при закрытии потока: %.1f с звука",
                         len(tail) / (16000 * 2))
                self._queue_phrase(tail)
        return {"closed": state is not None,
                "bytes": (state or {}).get("bytes", 0)}

    def _stream_credit(self, message: Envelope) -> dict:
        """Credit from the shell — for streams the core sends (4.0-F10)."""
        stream_id = message.payload.get("stream_id")
        extra = int(message.payload.get("bytes") or 0)
        if stream_id in self.data.open and extra > 0:
            self.data.grant(stream_id, extra)
            # Somebody may be standing over this very number. Waking on
            # the grant rather than polling for it: a poll would add its
            # own interval to every chunk of every reply, and the whole
            # point here is the milliseconds.
            with self._speech_room:
                self._speech_room.notify_all()
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

    def ask_machine(self, question: str, about: str = "") -> str:
        """
        Ask the shell about the computer, for a condition.

        Answers a string: the name of the program in front, or "1"/"" for
        "is it running". A string rather than a shape of its own because
        there are two questions and the answer to both is a fact about the
        moment — inventing a type for it would be inventing a vocabulary
        for a conversation of two words.
        """
        try:
            answer = self.ask_shell_sync("system.context",
                                         {"question": question,
                                          "about": about})
        except ProtocolFault:
            # No answer is not "no": a condition that cannot be
            # established is false, and the branch simply does not run.
            return ""
        return str(answer.get("answer", ""))

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
        # **A permission the person gave is a security event.** The
        # journal recorded the refusal of a dangerous tool and said
        # nothing about the moment somebody was asked for power over
        # the machine and said yes — which is the half one goes back to
        # the journal for. What is written is the answer, not what was
        # asked about: the request itself is already in the line above,
        # and the text of it belongs to the person.
        from core.logging_setup import security_log
        security_log().info("Разрешение %s пользователем",
                            "выдано" if granted else "не выдано")
        self.engine.answer_question(granted)

    # -- speech (4.0-E03, E04) --------------------------------------------------------

    #: What the ear has actually seen, stage by stage (`4.0-G`).
    #:
    #: Kept because three separate defects in this chain all looked the same
    #: from outside — "she cannot hear me" — while each broke at a different
    #: joint, and nothing anywhere said which. A chain of four links with no
    #: counters is debugged by guessing, and I guessed wrong twice.
    #:
    #: Counted, not logged per frame: sound arrives fifty times a second,
    #: and a line each would bury the journal it was meant to help.
    heard = {"bytes": 0, "frames": 0, "loud_frames": 0, "phrases": 0,
             "recognitions": 0, "texts": 0, "dropped": 0}

    #: What has already been said about the sound, so that it is not said
    #: again every twenty seconds. See `_say_what_is_heard`.
    _noted_stream = False
    _noted_quiet = False

    #: Phrases waiting their turn, and the one thread that takes them.
    #:
    #: **One thread, not one per phrase.** A phrase used to get a thread of
    #: its own, and the recogniser is a single object holding a single
    #: model loaded on first use. Two phrases close together meant two
    #: loads of the same model racing each other — "Failed to create a
    #: model" in the journal, once per phrase from then on — and two
    #: recognitions reading one model at once.
    #:
    #: What a person met was worse than an error. The words of one phrase
    #: surfaced during the **next** one, so Rina answered a second after
    #: they started speaking, and answered what they had said before. The
    #: journal shows it plainly: two phrases heard, one line of recognised
    #: text, and both phrases' words inside it.
    #:
    #: Order is the other half. Even with a thread-safe engine, results
    #: from parallel threads arrive in whatever order they finish, and a
    #: short phrase overtakes a long one. Commands are said in an order and
    #: mean something in that order.
    _phrases: "collections.deque | None" = None
    _stt_thread = None

    #: One lock for the queue and for whoever waits on it. A deque and a
    #: condition rather than `queue.Queue`, because the bound here means
    #: two different things at once — see `PHRASE_QUEUE` and
    #: `PART_QUEUE` — and a single `maxsize` can only say one of them.
    #:
    #: Woken with `notify_all`, never `notify`. There is one server to a
    #: running program but several to a check, and each has a queue of
    #: its own behind this one condition: `notify` woke whichever thread
    #: happened to be first in line, which was as likely as not somebody
    #: else's, and the phrase then waited for a wake-up that never came.
    _stt_wake = threading.Condition()

    #: Whether the absence of a voice has already been reported — see
    #: `_speak`. On the class, like the two above, so that a server put
    #: together field by field in a check has it too.
    _said_mute = False

    #: The last few things Rina said, to tell her own voice from a
    #: person's (`4.0b-E12`). The microphone stays open while she
    #: speaks, so her words come back through it; a phrase that is what
    #: she is saying is not a phrase anybody said to her.
    _lately_said: "collections.deque | None" = None

    #: How many of them to keep. Enough to cover what may still be
    #: playing while the next phrase is being recognised, and no more:
    #: this is an echo guard, not a memory of the conversation.
    ECHO_MEMORY = 4

    #: Raised when a person cuts in: what is still queued is thrown
    #: away rather than spoken over them.
    _cut_in = False

    #: Whether there is speech of hers in flight right now. Without it
    #: every phrase with her name in it — that is, most of them in
    #: "always listening" — would announce an interruption of nothing:
    #: a line in the journal, an event on the wire, and a word that
    #: stops meaning anything because it is said when nothing happened.
    _talking_out = False

    #: One reply at a time.
    #:
    #: **Two answers at once came out shuffled together.** Every reply
    #: is spoken on a thread of its own, and since `4.0b-E09` each one
    #: puts its sentences into the same queue one by one — so two
    #: threads put theirs in alternately. Reproduced outright: two
    #: replies of three sentences each left as
    #: `второй, первый, второй, первый, второй, первый`. A person met
    #: it by repeating a command they thought had not been heard.
    #:
    #: Not "the second waits its turn" but "the second replaces the
    #: first": she was asked something new, and finishing the old
    #: answer first is answering a question nobody is waiting for any
    #: more. The waiting is only until the old thread notices.
    _speak_guard = threading.Lock()

    #: Whether a reply is being made or sent right now — the thing a
    #: new one has to stop. Wider than `_talking_out`, which is only
    #: about the pushing: synthesis takes seconds of its own, and a
    #: reply interrupted during them must stop too.
    _reply_running = False

    #: How many phrases may wait. Recognition slower than speech has to
    #: lose something; what it must not do is fall further and further
    #: behind, answering a minute late. The oldest goes, and it is said out
    #: loud — silently dropping what a person said is the one thing worse.
    PHRASE_QUEUE = 4

    #: And how many **pieces** of a phrase in progress may wait, when the
    #: engine listens as it goes (`4.0b-E07`). A piece is a tenth of a
    #: second, so this is twenty seconds — longer than any one phrase.
    #:
    #: The overflow rule differs from the one above, because the items
    #: mean different things. Dropping the oldest of several phrases
    #: loses one of them; dropping the oldest piece of **one** phrase
    #: leaves a phrase with a hole in it, which is worse than no phrase
    #: at all — it is a phrase that says something else. So an overflow
    #: here abandons the phrase whole, and says so.
    PART_QUEUE = 200

    def _streaming(self) -> bool:
        """
        Whether the engine in use listens as the phrase is being said.

        Asked through `getattr` rather than as a plain attribute: a
        recogniser substituted in a check is somebody's small class, and
        the answer for anything that has not said otherwise is "no" —
        the path that works for every engine.
        """
        return bool(getattr(self.recogniser, "streams", False))

    def hearing(self) -> dict:
        """Where the sound got to. For the diagnostics and the checks."""
        return dict(self.heard)

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
        if self.heard["frames"] == 0:
            # Said once, and it is the line worth having. "Sound is
            # arriving" and "sound is not arriving" were indistinguishable
            # from outside, and telling them apart splits this chain in two
            # at the joint where it actually broke twice.
            #
            # **And in which mode.** Five minutes of a person's journal
            # said the sound was flowing and not a word about whether the
            # microphone was open by itself or because a button was
            # pressed — and the two differ in everything that follows: the
            # wake word, the search, the answer to a bare name. Reading
            # the journal, one had to guess, and I did, wrongly.
            log.info("Звук от оболочки пошёл: слушаю (%s)",
                     "всегда слушать"
                     if self.engine.is_always_listen()
                     else "по нажатию")
            # The model, before the first phrase needs it. In a person's
            # journal the first phrase of a session waited **eighteen
            # seconds** for the model to load, and eighteen seconds of
            # nothing is indistinguishable from not being heard. Started
            # here, the wait falls where a person has just done something
            # and expects a moment.
            #
            # In a thread of its own: this one carries the sound, and a
            # model loading on it would drop the phrase it was loaded for.
            if hasattr(self.recogniser, "warm"):
                threading.Thread(target=self.recogniser.warm,
                                 name="rina-stt-warm", daemon=True).start()

        self.heard["bytes"] += len(pcm)
        self.heard["frames"] += 1
        # The loudness the segmenter itself judges by, counted here so that
        # "the microphone is sending silence" can be told from "the
        # threshold is too high" — the two look identical from outside and
        # want opposite fixes.
        if speech.Segmenter.level(pcm) >= self.segmenter.threshold:
            self.heard["loud_frames"] += 1

        # **Said when it changes, not on a timer.** This used to write a
        # line every two hundred frames for as long as the microphone was
        # open, and in a real journal that came to two hundred and
        # seventy-five identical lines — the commonest entry in the file,
        # and the one carrying the least. A person who switches DEBUG on
        # to find out why she does not hear them then has to read past
        # it.
        #
        # What is worth a line is a change of picture: sound started
        # arriving; sound is arriving and none of it is loud enough to
        # cut a phrase out of. A stream that yields no phrase means the
        # loudness never crossed the threshold, and that is a different
        # complaint from silence with a different cure — so the two are
        # separate sentences and each is said once.
        self._say_what_is_heard()

        phrases = self.segmenter.feed(pcm)

        # **Listening as it goes, when the engine can** (`4.0b-E07`).
        # Handing over a finished phrase costs its whole recognition
        # after the person has stopped talking — 620 ms for Vosk on a
        # phrase of two and a half seconds. Fed as it goes, the same
        # engine gives the same words 4 ms after the last piece, because
        # everything but that piece is already done.
        #
        # What is fed is what the segmenter took into the phrase, not the
        # chunk that arrived: the two differ at the start of a phrase by
        # the run-up — the quiet beginning of the first word — and in
        # "always listening" the first word is the name.
        if self._streaming():
            if self.segmenter.taken:
                self._queue_part(self.segmenter.taken)
            if self.segmenter.gave_up:
                self._queue_part(None)          # too short: forget it

        for phrase in phrases:
            self.heard["phrases"] += 1
            log.info("Слышу фразу: %.1f с звука", len(phrase) / (16000 * 2))
            # Already fed, piece by piece — so what goes into the queue
            # is the order to finish, not the sound a second time.
            self._queue_phrase(None if self._streaming() else phrase)

    def _say_what_is_heard(self) -> None:
        """One line per change of what the microphone is doing."""
        loud = self.heard["loud_frames"] > 0
        # Half a second of sound before saying anything: the first frame
        # of a stream arrives before the person has drawn breath.
        if self.heard["frames"] < 25:
            return

        if not self._noted_stream:
            self._noted_stream = True
            log.debug("Звук пошёл: %d кадров", self.heard["frames"])

        # And once, when it becomes clear that sound is coming and
        # nothing is loud enough to be a phrase. Ten seconds of that is
        # a diagnosis, not a hiccup.
        if (not self._noted_quiet and not loud
                and self.heard["frames"] >= 500
                and self.heard["phrases"] == 0):
            self._noted_quiet = True
            log.warning(
                "Звук идёт, но ни один кадр не громче порога %.3f — "
                "фраз не будет", self.segmenter.threshold)

        # The other way round too: it was quiet, and now it is not.
        if self._noted_quiet and loud:
            self._noted_quiet = False
            log.debug("Громкие кадры пошли: %d", self.heard["loud_frames"])

    def _stt_queue(self) -> "collections.deque":
        """The queue, and the thread that empties it — made on first use."""
        with self._stt_wake:
            if self._phrases is None:
                self._phrases = collections.deque()
            if self._stt_thread is None or not self._stt_thread.is_alive():
                self._stt_thread = threading.Thread(
                    target=self._recognise_forever, args=(self._phrases,),
                    name="rina-stt", daemon=True)
                self._stt_thread.start()
            return self._phrases

    def _queue_part(self, part: "bytes | None") -> None:
        """A piece of the phrase now being said, or `None` to forget it."""
        waiting = self._stt_queue()
        with self._stt_wake:
            waiting.append(("part", part))
            if len(waiting) > self.PART_QUEUE:
                # See `PART_QUEUE`: a phrase with a hole in it says
                # something else, so the whole of it goes, and out loud.
                waiting.clear()
                self.heard["dropped"] += 1
                log.warning("Распознавание не поспевает: фраза брошена целиком")
            self._stt_wake.notify_all()

    def _queue_phrase(self, phrase: "bytes | None") -> None:
        """
        Put a finished phrase in the queue; see `_phrases` for why there is one.

        `None` means the sound has already been fed piece by piece and
        what is wanted now is the words.
        """
        waiting = self._stt_queue()
        with self._stt_wake:
            waiting.append(("phrase", phrase))
            # Only phrases carrying sound are counted against the bound:
            # one that has already been fed piece by piece is a marker
            # weighing nothing, and its backlog is the pieces, which have
            # a bound of their own.
            while True:
                heavy = [i for i, (kind, said) in enumerate(waiting)
                         if kind == "phrase" and said is not None]
                if len(heavy) <= self.PHRASE_QUEUE:
                    break
                gone = waiting[heavy[0]][1]
                del waiting[heavy[0]]
                self.heard["dropped"] += 1
                log.warning(
                    "Распознавание не поспевает: фраза на %.1f с отброшена",
                    len(gone) / (16000 * 2))
            self._stt_wake.notify_all()

    def _recognise_forever(self, waiting: "collections.deque") -> None:
        """
        Take what comes, one at a time, in the order it was said.

        Both the listening and the deciding happen here, on one thread:
        the pieces must reach the engine in order, and the worst single
        piece took 227 ms to think about — on the thread that reads the
        data channel that would be sound dropped on the floor.
        """
        while True:
            with self._stt_wake:
                while not waiting:
                    self._stt_wake.wait()
                kind, payload = waiting.popleft()
            try:
                if kind == "part":
                    if payload is None:
                        self.recogniser.reset()
                    else:
                        self.recogniser.feed(payload)
                else:
                    self._recognise(payload)
            except Exception:                           # noqa: BLE001
                # The thread is the only one there is: letting it die would
                # mean silence for the rest of the session, and silence is
                # how this whole chain fails invisibly.
                log.exception("Распознавание сорвалось")

    def _recognise(self, phrase: bytes) -> None:
        with trace_scope():
            if not self.recogniser.available():
                # Silence will not do here: the person will decide they
                # cannot be heard and start speaking louder.
                self.engine.bus.emit(
                    "assistant.error",
                    text="Распознавание недоступно: выберите модель в настройках.")
                return
            self.heard["recognitions"] += 1
            # `None` — the sound was fed piece by piece while it was
            # being said, and what is left is to ask for the words.
            outcome = (self.recogniser.finish() if phrase is None
                       else self.recogniser.recognise(phrase))
            if not outcome.ok:
                log.warning("Распознавание не сложилось: %s", outcome.error)
                self.engine.bus.emit(
                    "assistant.error",
                    text=f"Не удалось распознать: {outcome.error}")
                return
            if not outcome.text:
                log.info("Фраза распозналась пустой — тишина или шум")
                return          # silence is neither an error nor worth reporting

            if self._is_her_own(outcome.text):
                # Her own voice, through the open microphone. Said at
                # debug: this happens on every reply and is normal, and
                # a journal that reports the normal buries the rest.
                log.debug("Это её собственные слова, не в счёт: %s",
                          safe(outcome.text))
                return

            self.heard["texts"] += 1
            log.info("Распознано: %s", safe(outcome.text))

            # **Cut in.** Addressed by name or told to stop while she is
            # talking — the speech breaks off there and then. Sending is
            # stopped as well as playing: a second of sound already lies
            # in the shell's queue, and a second of talking over somebody
            # who has just interrupted is the whole of what interrupting
            # is against.
            from voice import wake as wake_mod

            hushed = wake_mod.hush_asked(outcome.text)
            named = bool(wake_mod.find_wake(
                outcome.text, wake_mod.get_wake_words(self._settings() or {}))[0])
            if hushed or named:
                self.hush()
            if hushed:
                # "Stop" is not a command to carry out afterwards: it
                # was about the talking, and the talking has stopped.
                self.engine.bus.emit("speech.recognized", text=outcome.text)
                return

            # The recognised words are announced before anything is decided
            # about them, and that is deliberate: a person must see what was
            # heard even when it is not acted on. Otherwise "she ignored me"
            # and "she misheard me" are the same silence.
            self.engine.bus.emit("speech.recognized", text=outcome.text)

            # The wake word is demanded while "always listening" is on, and
            # only then. Without this the streamed path acted on every
            # phrase in the room: the old path asked for the wake word in
            # `_always_worker`, which the shell's audio does not go through.
            self.engine.handle_command_async(
                outcome.text, source="voice",
                require_wake=self.engine.is_always_listen())

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
        #
        # **Everything the builders read, not only the engine's name.**
        # `recogniser_for` builds Vosk out of `vosk_model` and Whisper out
        # of `whisper_model`; comparing the names alone meant that picking
        # a model changed nothing until the core was restarted, and the
        # person who had just chosen a model heard "recognition is
        # unavailable, choose a model in settings". The list is here rather
        # than in `speech.py` on purpose: it is the question "what makes
        # this stale", and it belongs with the staleness.
        wanted = tuple(str(store.get(key, "") or "") for key in _VOICE_KEYS)
        if wanted == self._speech_wanted:
            return
        self._speech_wanted = wanted
        if not self._speech_given[1]:
            self.synthesiser = speech.synthesiser_for(store)
        if not self._speech_given[0]:
            # What the old one had been fed goes with it. A phrase begun
            # on one engine and finished on another is not a phrase.
            if self._streaming():
                self.recogniser.reset()
            self.recogniser = speech.recogniser_for(store)
            self.segmenter.flush()

    def _is_her_own(self, said: str) -> bool:
        """Is this what Rina is saying right now, come back through the air?"""
        from voice.textmatch import normalize, similar

        heard = normalize(said)
        if not heard or self._lately_said is None:
            return False
        for mine in self._lately_said:
            spoken = normalize(mine)
            if not spoken:
                continue
            # Inside, or close to the whole of it: recognition of one's
            # own voice through a speaker is imperfect, and demanding an
            # exact match would let every second echo through.
            if heard in spoken or similar(heard, spoken, threshold=0.72):
                return True
        return False

    def hush(self) -> None:
        """
        Stop talking: throw away what is queued and tell the shell to cut.

        Both halves matter. Stopping the sending leaves up to a second
        of sound already in the shell's queue; stopping the playing
        leaves the rest of the reply still to come. A person who
        interrupted hears the difference immediately.
        """
        if not (self._reply_running or self._talking_out
                or (self._speech_queue and not self._speech_queue.empty())):
            return          # there was nothing to interrupt
        self._cut_in = True
        waiting = self._speech_queue
        if waiting is not None:
            while True:
                try:
                    waiting.get_nowait()
                except queue.Empty:
                    break
        log.info("Перебили — замолкаю")
        self.send(Envelope.event("speech.stop", {}, id=self.ids.next()))

    def _speak(self, text: str) -> None:
        """
        Synthesise and send to the shell.

        Synthesis in the core, playback in the shell: the models live where
        the ML ecosystem is, and the sound where latency is low and audio is
        native.
        """
        self._voice_follows_settings()
        if not self.synthesiser.available():
            # The text already went as an event; there is simply no voice.
            # Said in the journal once, because a mute Rina is otherwise
            # indistinguishable from a broken one — and on a machine
            # without a synthesis package she is mute from the first
            # minute, with nothing anywhere to say why.
            if not self._said_mute:
                self._said_mute = True
                log.info("Голоса нет (%s): %s. Ответы остаются текстом.",
                         getattr(self.synthesiser, "name", "?"),
                         getattr(self.synthesiser, "last_error", "")
                         or "движок синтеза недоступен")
            return
        # Replies queue here rather than cut in on each other: a
        # reminder going off in the middle of an answer must not take
        # the rest of that answer with it. What **does** cut is a new
        # command — the person asked something else — and that is
        # decided where commands are, in `RinaEngine.handle_command`.
        with self._speak_guard:
            self._reply_running = True
            try:
                self._say_it(text)
            finally:
                self._reply_running = False

    #: When the current reply began, and when its first sound existed.
    #: Held on the server because two methods fill them in: the streaming
    #: branch and the whole-file fallback.
    _said_from = 0.0
    _first_sound = None

    def _say_it(self, text: str) -> None:
        voice = str(self._settings().get("voice", "") if self._settings()
                    else "")
        rate = int((self._settings() or {}).get("speed", 100) or 100)

        # **Sentence by sentence** (`4.0b-E09`). Synthesis of a whole
        # reply is waited out whole: the person hears nothing until the
        # last byte of the last word exists. Sent a sentence at a time,
        # the first is already playing while the rest is still being
        # made — and `send_speech` queues rather than blocks, so this
        # loop does not wait for the sound to be heard either.
        #
        # The wait before the first syllable then stops depending on how
        # long the answer is, which is what made long answers feel like
        # a hang rather than a pause.
        #
        # What she is about to say, so that hearing it back does not
        # count as somebody saying it — see `_is_her_own`.
        if self._lately_said is None:
            self._lately_said = collections.deque(maxlen=self.ECHO_MEMORY)
        self._lately_said.append(text)

        self._cut_in = False
        spoken = 0.0
        # Where the wait before she speaks actually goes.
        #
        # «Ответ за секунду, а заговорила через шестнадцать» is a report
        # nobody could act on: the path runs through synthesis, a pipe,
        # credit and somebody else's audio device, and every one of them
        # is a plausible culprit to a person guessing. So the core says
        # its own half out loud — one line per reply — and the guessing
        # stops at the process boundary. This is the first of the three
        # numbers `4.0s-S5` wants in the regression.
        began = self._said_from = time.monotonic()
        self._first_sound = None
        pieces = list(speech.sentences(text))
        for piece in pieces:
            if self._cut_in:
                log.info("Остаток реплики не сказан: перебили")
                break
            said = self._stream_speech(piece, voice, rate)
            if said:
                spoken += said
                continue
            pcm = self.synthesiser.synthesize(piece, voice=voice, rate=rate)
            if not pcm:
                # One piece failing is not the whole reply failing: what
                # was already said stays said, and going quiet about the
                # rest is worse than saying most of it.
                log.warning("Не синтезировалось: %s", safe(piece))
                continue
            spoken += len(pcm) / 2 / max(self.synthesiser.sample_rate, 1)
            if self._first_sound is None:
                self._first_sound = time.monotonic() - began
            self.send_speech(pcm, self.synthesiser.sample_rate)

        log.info("Речь (%s): до первого звука %s, вся реплика %d мс, "
                 "речи %.1f с, предложений %d",
                 getattr(self.synthesiser, "name", "?"),
                 ("%d мс" % (self._first_sound * 1000)
                  if self._first_sound is not None else "не было"),
                 (time.monotonic() - began) * 1000, spoken, len(pieces))

        # The conversation's window belongs to the person, so it starts
        # when they can speak — after she stops. See
        # `RinaEngine.talk_after_speaking`.
        if spoken:
            self.engine.talk_after_speaking(spoken)

    def _stream_speech(self, piece: str, voice: str, rate: int) -> float:
        """
        Send one sentence as it is made. Returns the seconds of sound sent.

        Zero means this engine cannot stream — or gave out nothing.

        **`4.0b-E10`.** Even a single sentence is waited out whole today:
        the request goes, and nothing is heard until the last byte of it
        comes back. Sent as it arrives, the first sound leaves for the
        shell while the rest of the sentence is still being spoken on
        somebody else's computer.

        A sentence that gave out nothing at all falls back to the whole
        path — the engine may simply have failed, and one more attempt
        costs a wait but saves a silence. A sentence that broke off in
        the middle does not: what was heard was heard, and saying the
        first half twice is worse than losing the second.
        """
        if not getattr(self.synthesiser, "streams", False):
            return 0.0
        sent = 0.0
        try:
            for pcm in self.synthesiser.stream(piece, voice=voice, rate=rate):
                if not pcm:
                    continue
                if self._first_sound is None:
                    self._first_sound = time.monotonic() - self._said_from
                sent += len(pcm) / 2 / max(self.synthesiser.sample_rate, 1)
                self.send_speech(pcm, self.synthesiser.sample_rate)
        except Exception:                               # noqa: BLE001
            log.exception("Потоковый синтез сорвался")
        return sent

    #: Sound waiting to go to the shell, and the thread that sends it.
    #:
    #: **Sending waits, and waiting needs somewhere to wait.** The credit
    #: comes back as the shell plays — a fifth of a second per chunk — so
    #: whoever sends has to stand still for whole seconds. That cannot be
    #: the thread that answered `speech.test`: it is the control channel's
    #: dispatcher, and standing still there means every other request
    #: waits out the reply being spoken.
    _speech_queue: "queue.Queue | None" = None
    _speech_sender = None
    _speech_guard = threading.Lock()

    #: Woken when credit arrives — see `_room_for`. On the class, like the
    #: guard above: there is one core to a process, and a server put
    #: together field by field in a check needs it as much as a real one.
    _speech_room = threading.Condition()

    #: How long one chunk may wait for credit. Playback of a chunk is
    #: about a fifth of a second; ten is not "slow machine" but "the other
    #: side is not playing at all", and then it is better to stop and say
    #: so than to hold a reply for ever.
    SPEECH_WAIT = 10.0

    def send_speech(self, pcm: bytes, sample_rate: int) -> None:
        """
        Send ready-made sound to the shell over the data channel.

        Queued rather than sent here: see `_speech_queue`. The caller gets
        its thread back at once, which matters because one of the callers
        is the dispatcher.
        """
        if self.channels.data is None or not pcm:
            return
        with self._speech_guard:
            if self._speech_queue is None:
                self._speech_queue = queue.Queue()
            waiting = self._speech_queue
            if self._speech_sender is None or not self._speech_sender.is_alive():
                self._speech_sender = threading.Thread(
                    target=self._send_speech_forever, args=(waiting,),
                    name="rina-speech", daemon=True)
                self._speech_sender.start()
        waiting.put((pcm, sample_rate))

    def _send_speech_forever(self, waiting: "queue.Queue") -> None:
        """Take utterances one at a time, in the order they were said."""
        while True:
            pcm, sample_rate = waiting.get()
            try:
                self._push_speech(pcm, sample_rate)
            except Exception:                           # noqa: BLE001
                # The thread is the only one there is: letting it die
                # would mean a silent Rina for the rest of the session.
                log.exception("Отправка речи сорвалась")

    def _room_for(self, size: int) -> bool:
        """
        Wait until there is credit for this much. `False` — nobody is taking it.

        **This is where the reply used to be thrown away.** The loop below
        broke off at the first shortfall, and the shortfall came at once:
        the initial self-issued credit is 32 KB, that is two thirds of a
        second of sound, and the loop runs through in microseconds — far
        sooner than the shell could return credit for what it had played.
        Measured on an eight-second reply: 32832 bytes went out of 384000,
        and nothing said so. A person heard speech that breaks off.
        """
        edge = time.monotonic() + self.SPEECH_WAIT
        with self._speech_room:
            while self.data.available(self._speech_stream) < size:
                if not self._running or self.channels.data is None:
                    return False
                left = edge - time.monotonic()
                if left <= 0:
                    return False
                self._speech_room.wait(min(left, 0.2))
        return True

    def _push_speech(self, pcm: bytes, sample_rate: int) -> None:
        self._talking_out = True
        try:
            self._push_speech_now(pcm, sample_rate)
        finally:
            self._talking_out = False

    def _push_speech_now(self, pcm: bytes, sample_rate: int) -> None:
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
            # out at once. So we give ourselves enough to start speaking and
            # after that live by what is issued.
            #
            # Enough to **start**, not enough to finish. Half a megabyte was
            # ten seconds of sound, which the shell could not hold and
            # silently threw away: the person heard fragments of words all
            # through the reply. A self-issued credit larger than the
            # receiver's queue is not a head start, it is the backpressure
            # switched off.
            self.data.grant(self._speech_stream, 32 * 1024)

        chunk = 8192
        for offset in range(0, len(pcm), chunk):
            if self._cut_in:
                return          # interrupted: the rest is not sent
            piece = pcm[offset:offset + chunk]
            if not self._room_for(len(piece)):
                # Said out loud. Cutting a reply short may be the only
                # thing left to do when the other side has stopped
                # playing, but doing it in silence is what made this cost
                # a day: neither journal had a line, and the failure
                # arrived as "her speech glitches sometimes".
                log.warning("Речь оборвана: оболочка не вернула кредит за "
                            "%.0f с, не отправлено %d Б из %d",
                            self.SPEECH_WAIT, len(pcm) - offset, len(pcm))
                return
            self.channels.data.send(self.data.send(self._speech_stream, piece))

    # -- the break ---------------------------------------------------------------

    def on_disconnect(self) -> dict[str, int]:
        """
        The shell has gone: reset everything volatile (§13).

        The core ends after this — see the module header.
        """
        return self.volatile.reset()
