"""
The assistant's core: recognition, the command pipeline, speech, reminders.

There is not one Qt import here — and that is the module's chief property.
The core can be started without a window (in tests, from the console, in a
separate process), and the shell subscribes to the bus's events and decides
how to show them.

The division of duties:
  the core  — what to do: understand the phrase, perform it, answer, plan;
  the shell — how it looks: windows, pop-up hints, the tray icon.

Everything blocking (the microphone, speech synthesis, pauses in sequences)
goes into background threads: the core must not depend on who called it.
"""

import queue
import contextvars
import threading
import time

from core.events import bus
from core.trace import trace_scope
from core.i18n import t as tr
from core import router as router_mod
from core import dialog as dialog_mod
from core.dialog import Dialog, Question
from core.executor import Executor
from core.toolrunner import NO_SHELL, ToolContext, ToolRunner
from voice.wake import get_wake_words
from voice.reminders import ReminderStore
from voice.sessions import SessionStore
from voice.todo import TodoStore
from core.logging_setup import get_logger, safe, security_log
from core.protocol import Events
from core.features import default_features
from core.settings_api import default_settings
from voice import stt as stt_mod
from voice import tts as tts_mod
from voice.commands import handle_builtin_command
from voice.history import HistoryStore
from voice.user_commands import UserCommandStore


log = get_logger("engine")


class RinaEngine:
    """The assistant's logic, independent of the interface."""

    # after a minute a question that was asked counts as stale
    PENDING_TTL = 60

    # The words of consent and refusal live in the router: they are part of
    # parsing, and the router is obliged to work without raising the core.
    # Here are aliases, so that references to RinaEngine.YES_WORDS need not
    # change through the code and in the tests.
    YES_WORDS = router_mod.YES_WORDS
    NO_WORDS = router_mod.NO_WORDS

    def __init__(self, plugin_manager=None, event_bus=None, settings=None,
                 features=None):
        """
        settings — any object matching core.settings_api.SettingsProvider.
        By default the application's shared store; in tests MemorySettings,
        so as not to touch the user's file.

        features — matching core.features.FeatureProvider. By default the
        free plan, where everything is available.
        """
        self.bus = event_bus or bus
        #: Who speaks instead of the local speaker. Set by the protocol's
        #: server side (4.0-E04); until it is set, the core speaks itself, as
        #: in 3.1.0 — the Qt windowed application uses exactly this.
        self.voice_out = None
        #: Who touches the machine instead of the core itself (4.0-G01,
        #: ADR 0009). Until it is set, the core acts itself, as in 3.1.0.
        self.system_out = None
        #: Who listens to the microphone instead of the core (`4.0-G`).
        #:
        #: The microphone belongs to the shell for exactly the reason
        #: launching programs and system actions do: whoever parses speech
        #: must not hold the device. Until this is set the core listens for
        #: itself — that is how 3.1.0 works, where there is no shell at all.
        #:
        #: It exists because the declared 4.0 path had never once run. The
        #: shell sent sound, the core piled it into the segmenter — and both
        #: a single listen and "always listening" opened **their own**
        #: microphone and never looked at that sound. Two sets of ears, and
        #: the one working was the one the architecture says must not.
        self.ears_outside = False

        #: Where to get the program index from. In 4.0 that is the shell
        #: (4.0-G06): the registry and the Start menu are Windows data, and
        #: reading them from a process that is obliged to work without
        #: Windows means settling half of win32 inside the core.
        self.apps_source = None
        #: Called when the engine writes a setting itself — see
        #: `_settings_changed`. Set from outside, like `voice_out`.
        self.settings_changed = None
        #: Called to cut off speech in progress — see `_hush_previous`.
        self.hush_out = None
        self._apps_cache = None
        #: Who opens a page in a browser. The same place as the rest of what
        #: touches the machine; until it is set, the core opens it itself,
        #: as in 3.1.0.
        self.browser_out = None

        #: Who creates the process. The shell too (4.0-G05).
        self.launch_out = None
        #: Who to tell about a question that was asked (4.0-F11). Set by the
        #: server side: only the shell can ask a person.
        self.on_question = None
        self._settings = settings if settings is not None else default_settings()
        self._features = features if features is not None else default_features()
        settings = self._settings          # a local name for the code below
        self._plugins = plugin_manager
        self._busy = False
        self._always_listen = False
        self._always_thread = None
        self._stop_always = threading.Event()

        #: Until when the wake word may be left out, because a
        #: conversation is going on (`4.0b-E06`).
        #:
        #: The complaint that started this: "the activation word has to be
        #: said before every phrase". A person says a name once and then
        #: talks; saying it again before each sentence is addressing a
        #: machine, not speaking to somebody.
        self._talking_until = 0.0
        self._talking_since = 0.0
        self._talk_timer = None

        #: Whether the shell has been told the microphone is wanted. See
        #: `_hold_ear`: two things hold it, and only one of them can
        #: speak at a time.
        self._ear_open = False
        self._cmd_store = UserCommandStore(settings)
        self._history = HistoryStore(settings)
        self._host = None                    # actions on the window (see set_host)
        # "Rina is speaking right now". We count speakers rather than
        # keeping one flag: with overlapping replies the first to finish
        # cleared the flag, the microphone opened under speech still
        # sounding, and Rina heard herself.
        self._speaking = threading.Event()

        #: What was launched last — as the person said it (`4.0b-A04`).
        #:
        #: In memory rather than in the store: a correction follows a
        #: launch, in the same conversation. A "last" that survived a
        #: restart would refer to a session the person no longer remembers,
        #: and would teach the wrong thing.
        self._last_launch_query = ""
        self._speak_lock = threading.Lock()
        self._speak_count = 0
        self._reminders = ReminderStore(settings)
        self._todo = TodoStore(settings)
        self._sessions = SessionStore(settings)
        #: What is in front, and since when (`4.0b-A02`). A pair,
        #: not a history: see `_credit_foreground`.
        self._in_front = ("", 0.0)
        #: What focus mode is holding back (`4.0b-A05`). One, not a
        #: queue — see `offer`.
        self._held_offer = None

        # Parsing, memory of the question asked, and execution are separated
        # into distinct objects (4.0-B02, B03, B04). The core ties them
        # together.
        self._dialog = Dialog()

        # Everything that changes the world goes through the tool registry
        # (4.0-C03). The executor below does nothing itself — it turns
        # intents into calls.
        self._tools = ToolRunner(
            ToolContext(
                settings=settings,
                reminders=self._reminders,
                todo=self._todo,
                sessions=self._sessions,
                release_held=lambda: self.release_held(),
                commands=self._cmd_store,
                plugins=plugin_manager,
                # Through a lambda rather than a bound method: the core may
                # substitute speech and the bus later (tests, the shell), and
                # the tools are obliged to follow the current one rather than
                # the one that existed at assembly time.
                emit=lambda name, **data: self._emit(name, **data),
                host=None,
                on_alias=self._remember_choice,
                # Through a lambda for the same reason as speech: the shell
                # appears later than the tools are assembled.
                # `NO_SHELL` is a code rather than a phrase: the registry
                # branches on it, and prose would have to be matched by
                # substring — which breaks on the first translation.
                system_out=lambda action: (self.system_out(action)
                                           if self.system_out else
                                           (False, NO_SHELL)),
                open_url=lambda url: (self.browser_out(url)
                                     if self.browser_out else
                                     (False, NO_SHELL)),
                launch_app=lambda launch, kind: (
                    self.launch_out(launch, kind) if self.launch_out
                    else (False, NO_SHELL)),
                # The same list as the router's: see `_apps`.
                apps=self._apps,
                # For "Why?" (`4.0b-B04`). Through lambdas because the
                # runner is being built on this very line: the journal and
                # the registry belong to it, and taking them now would take
                # them from an object that does not exist yet.
                journal=lambda: None,
                registry=lambda: None,
            ),
            features=self._features,
        )

        # And now that the runner exists, the two fields point at its own
        # journal and its own registry. An explanation must come out of the
        # journal that is actually being written to; a second one would
        # agree with the first only by accident.
        self._tools._ctx.journal = self._tools.audit
        self._tools._ctx.registry = self._tools._registry

        # A plugin's tools are created and removed together with the plugin
        # (`4.0-H03`). A subscription rather than a one-off walk: a plugin is
        # switched on and off at any moment, and the registry is obliged to
        # follow that.
        if plugin_manager is not None:
            plugin_manager.changed.connect(self._sync_plugin_tools)
            self._sync_plugin_tools()

            # A plugin speaks through the core rather than by itself: it has
            # neither a voice nor a window. In 3.1.0 the application's window
            # listened to its line; there is no window any more, and without
            # this subscription a plugin wrote a note and said nothing about
            # it.
            plugin_manager.response.connect(
                lambda plugin_id, text: self.say(text))
        self._executor = Executor(
            say=lambda text, sound="response": self.say(text, sound=sound),
            tools=self._tools,
            emit=lambda name, **data: self._emit(name, **data),
        )

        # the reminder scheduler: an ordinary thread, not an interface timer
        self._stop_reminders = threading.Event()
        self._reminder_thread = None

        # The command queue. The pipeline launches programs, goes to the
        # network and waits for the model's answer — in the interface thread
        # that is seconds of a frozen window. One queue for every source: the
        # pipeline holds shared state (an unclosed clarifying question), and
        # parallel handling spoils it.
        self._commands = queue.Queue()
        self._command_worker = None
        self._command_lock = threading.Lock()

    # ------------------------------------------------------------------
    # events
    # ------------------------------------------------------------------
    def _emit(self, name, **payload):
        self.bus.emit(name, **payload)

    @property
    def features(self):
        """
        The availability of capabilities. Ask only here.

        The shell shows the state but does not decide it: the decision is
        taken by the core, or it could be circumvented from the interface
        (4.0-B08).
        """
        return self._features

    def set_host(self, host):
        """host performs actions on the window (minimise/show/quit)."""
        self._host = host
        self._tools._ctx.host = host
        self._executor._host = host

    # ------------------------------------------------------------------
    # speech
    # ------------------------------------------------------------------
    def say(self, text, sound="response"):
        """Answer: write to the history, tell the shell, and say it out loud."""
        from voice import sounds

        if sound == "response":
            sounds.play_response(self._settings)
        elif sound == "error":
            sounds.play_error(self._settings)

        self._history.add("assistant", text)
        self._emit(Events.HISTORY_CHANGED)
        self._emit(Events.RESPONSE, text=text)
        threading.Thread(target=self._speak_blocking, args=(text,),
                         daemon=True).start()

    def _speak_blocking(self, text):
        if not self._settings.get("voice_reply", True):
            return  # the "stay silent" mode: text only, no voice

        # If somebody outside takes the voice, they take it whole. In the
        # split program that is the shell (4.0-E04): the core synthesises,
        # the shell plays. There must not be two paths, or one and the same
        # line will one day sound twice — from the shell's speaker and from
        # the core's.
        if self.voice_out is not None:
            self._begin_speaking()
            try:
                self.voice_out(text)
            except Exception as e:                       # noqa: BLE001
                self._emit(Events.ERROR, text=tr("Ошибка озвучки: ") + str(e))
            finally:
                self._end_speaking()
            return

        engine = tts_mod.get_engine(self._settings.get("tts_engine", "silent"))
        self._begin_speaking()
        try:
            engine.speak(
                text,
                voice=self._settings.get("voice"),
                volume=int(self._settings.get("volume", 75)),
                rate=int(self._settings.get("speed", 100)),
            )
        except Exception as e:
            self._emit(Events.ERROR, text=tr("Ошибка озвучки: ") + str(e))
        finally:
            # a pause after speech, so the "tail" does not get back into the microphone
            time.sleep(0.4)
            self._end_speaking()

    def _begin_speaking(self):
        with self._speak_lock:
            self._speak_count += 1
            self._speaking.set()

    def _end_speaking(self):
        with self._speak_lock:
            self._speak_count = max(0, self._speak_count - 1)
            if self._speak_count == 0:
                self._speaking.clear()

    def _wait_while_speaking(self):
        while self._speaking.is_set() and not self._stop_always.is_set():
            time.sleep(0.1)

    # ------------------------------------------------------------------
    # the microphone
    # ------------------------------------------------------------------
    def listen_once(self):
        """A single listen (on a hotkey)."""
        if self._busy:
            return
        self._busy = True
        threading.Thread(target=self._listen_worker, daemon=True).start()

    def _listen_worker(self):
        from voice import sounds

        sounds.play_activation(self._settings)

        # With a shell the core does not touch the microphone: it has
        # announced that it is listening, and the sound will arrive over the
        # data channel. `_hear` cuts it into phrases and starts recognition
        # itself — what is left here is to hold the window open and say when
        # it closed.
        if self.ears_outside:
            self._hold_ear()
            try:
                time.sleep(self.listen_seconds())
            finally:
                self._busy = False
                # And **not** "stopped" outright: the mode may still be
                # holding the ear. See `_hold_ear`.
                self._hold_ear()
            return
        self._emit(Events.LISTENING_STARTED)

        result = None
        try:
            engine = stt_mod.get_engine(self._settings.get("stt_engine", "disabled"))
            result = engine.listen_once(
                language=self.lang_code(),
                timeout=self.listen_seconds(),
            )
        except Exception as e:
            # There used to be only a finally here: the indicator went out,
            # the exception carried off the thread, and the user saw that
            # "nothing happened", without a single hint as to why.
            log.exception("Сбой распознавания")
            self.say(tr("Не получилось распознать речь: ") + str(e),
                     sound="error")
            return
        finally:
            self._emit(Events.LISTENING_STOPPED)
            self._busy = False

        if result is None:
            return
        if result.ok and result.text:
            self._emit(Events.RECOGNIZED, text=result.text)
            # on a hotkey the wake word is not needed: the user has already called explicitly
            self.handle_command_async(result.text, require_wake=False,
                                      source="voice")
        elif result.error:
            # the engines give the error text in Russian — we translate at the boundary
            self._emit(Events.ERROR, text=tr(result.error))

    #: How long a conversation stays open after the last thing said.
    #:
    #: Long enough to draw breath and go on; short enough that a phrase
    #: said to somebody else in the room a minute later is not taken for a
    #: command. Fifteen seconds is about as long as a pause can be and
    #: still belong to the same exchange.
    TALK_WINDOW = 15.0

    #: And how long one conversation may last altogether.
    #:
    #: **The boundary written into the plan.** An open conversation is an
    #: open ear — the same surface as `T-19` — and it has to be finite,
    #: visible, and close itself. Extended turn by turn without a ceiling
    #: it would satisfy the first two and quietly fail the third: an
    #: afternoon of talking near the machine would leave the word
    #: optional until the program was shut down.
    TALK_LIMIT = 180.0

    def _hold_ear(self):
        """
        Say whether sound should be coming at all — once, for everybody.

        **Two things hold the microphone open** — the "always listening"
        mode and a one-off listen on a hotkey — and each of them used to
        announce its own beginning and end. The shell believes the last
        thing it was told, so a one-off listen inside the mode said
        "stopped" when its eight seconds ran out, the shell shut the
        microphone, and the mode went on being on with nothing listening.
        A person met that as "always listening does not work — she does
        not hear me", and then as the same thing on the hotkey: eight
        seconds of hearing and silence after.

        So the question is asked of the engine rather than of whoever
        happens to be finishing: is anybody still holding the ear open.
        A release is only a release when the last holder lets go.
        """
        wanted = bool(self._always_listen or self._busy)
        if wanted == self._ear_open:
            return
        self._ear_open = wanted
        self._emit(Events.CAPTURING, active=wanted)
        self._emit(Events.LISTENING_STARTED if wanted
                   else Events.LISTENING_STOPPED)
        log.info("Микрофон %s (режим %s, разовое %s)",
                 "открыт" if wanted else "закрыт",
                 "вкл" if self._always_listen else "выкл",
                 "идёт" if self._busy else "нет")

    def talking(self, now=None):
        """Is a conversation open right now."""
        now = time.monotonic() if now is None else now
        return now < self._talking_until

    def talk_after_speaking(self, seconds):
        """
        Her own reply must not eat the conversation's window.

        **The whole feature was unusable because of this.** The window
        opens when the phrase is understood, and then Rina answers: a
        second or two before the first sound, nine seconds of speech.
        By the time the person can say the next thing without her name,
        fifteen seconds have gone and the window has closed — met in a
        person's journal three times in a row, thirty seconds between
        "что ты умеешь" and the answer to it:

            `13:11:55  Команда (voice): 'что ты умеешь?'`
            `13:12:25  'Хорошо, запустите им.'`
            `13:12:26  Расслышано, но не мне (wake)`

        The window is a person's opportunity to speak, so it has to
        begin when they **can** speak — after she stops. The length of
        the reply is known exactly: it is the sound that was sent.
        """
        if not self.talking():
            return          # nothing to hold open
        self._open_talk(after=max(0.0, float(seconds)))

    def _open_talk(self, after=0.0):
        """
        Start a conversation, or push its end further off.

        `after` is how much of what follows is Rina talking: the window
        is measured from the end of that, not from now.
        """
        now = time.monotonic()
        fresh = not self.talking(now)
        if fresh:
            self._talking_since = now

        # The ceiling wins over the extension: the last exchange of a long
        # conversation gets a shorter window, and then it is over.
        until = min(now + after + self.TALK_WINDOW,
                    self._talking_since + self.TALK_LIMIT)
        if until <= now:
            self._close_talk()
            return

        self._talking_until = until
        self._emit(Events.CONVERSATION, open=True,
                   seconds=round(until - now, 1))
        self._arm_talk_timer()

    def _close_talk(self):
        """End the conversation: the wake word is needed again."""
        if self._talk_timer is not None:
            self._talk_timer.cancel()
            self._talk_timer = None
        if self._talking_until == 0.0:
            return
        self._talking_until = 0.0
        self._talking_since = 0.0
        self._emit(Events.CONVERSATION, open=False, seconds=0.0)

    def _arm_talk_timer(self):
        """
        Close it by the clock, not by the next phrase.

        A conversation that ended only when something else was said would
        be open for hours in a quiet room, and nothing would say so. It
        closes itself, and the closing is announced — that is two thirds
        of the boundary this feature was given.
        """
        if self._talk_timer is not None:
            self._talk_timer.cancel()
        left = max(0.05, self._talking_until - time.monotonic())
        self._talk_timer = threading.Timer(left, self._talk_ran_out)
        self._talk_timer.daemon = True
        self._talk_timer.start()

    def _talk_ran_out(self):
        # Extended while the timer was waiting: rearm rather than close.
        if self.talking():
            self._arm_talk_timer()
            return
        self._close_talk()

    def set_always_listen(self, on):
        on = bool(on)
        if on == self._always_listen:
            return
        self._always_listen = on

        # Written down, not only remembered. The setting existed in the
        # store's defaults and was read by nobody and written by nobody: the
        # dialogue page asked settings for it and got the default every
        # time, so the switch showed "off" while the mode was on. A person
        # met that as the button resetting whenever they changed tabs.
        try:
            self._settings.set("always_listen", on)
            self._settings.save()
        except Exception:                                # noqa: BLE001
            log.exception("Не удалось запомнить режим «всегда слушать»")

        self._emit(Events.ALWAYS_LISTEN, enabled=on)
        # A conversation belongs to an open microphone. Switching the mode
        # off leaves it hanging otherwise: the word would still be
        # optional for the next quarter minute, with nothing listening.
        if not on:
            self._close_talk()
        if on:
            # every start has its own stop flag: an old thread may still be
            # waiting on the microphone, and a shared cleared flag would
            # leave it running — then one phrase was recognised and performed
            # twice
            self._stop_always = threading.Event()
            self._always_thread = threading.Thread(
                target=self._always_worker, args=(self._stop_always,),
                daemon=True)
            self._always_thread.start()
        else:
            self._stop_always.set()

    def is_always_listen(self):
        return self._always_listen

    def _always_worker(self, stop_flag=None):
        stop_flag = stop_flag or self._stop_always

        # With a shell the listening window stays open while the mode is
        # on: the sound arrives by itself, `_hear` cuts it into phrases, and
        # the wake word is required — checked in the same place as it is for
        # typed text.
        if self.ears_outside:
            self._hold_ear()
            try:
                while not stop_flag.wait(0.2):
                    pass
            finally:
                # The mode is already off by the time we are here — the
                # flag is what woke us — so this asks the same question
                # and gets the right answer even if a one-off listen is
                # running.
                self._hold_ear()
            return

        engine = stt_mod.get_engine(self._settings.get("stt_engine", "disabled"))
        if engine.id == "disabled":
            self._emit(Events.ERROR, text=tr(
                "Режим «всегда слушать» требует выбранного движка распознавания."))
            self._always_listen = False
            self._emit(Events.ALWAYS_LISTEN, enabled=False)
            return

        while not stop_flag.is_set():
            # while Rina is speaking we do not listen, or her own voice gets recognised
            if self._speaking.is_set():
                self._wait_while_speaking()
                continue

            self._emit(Events.CAPTURING, active=True)
            try:
                result = engine.listen_once(language=self.lang_code(), timeout=5)
            except Exception:
                result = stt_mod.STTResult(error="listen error")
            self._emit(Events.CAPTURING, active=False)

            if stop_flag.is_set():
                break
            if result.ok and result.text:
                # here the wake word is obligatory: otherwise the assistant
                # would react to any conversation in the room
                self.handle_command_async(result.text, require_wake=True,
                                          source="always", wait=True)
                self._wait_while_speaking()

    # ------------------------------------------------------------------
    # reminders
    # ------------------------------------------------------------------
    def start_reminders(self):
        """Starts checking what is planned (once a second, in the background)."""
        if self._reminder_thread is not None:
            return
        self._stop_reminders.clear()
        self._reminder_thread = threading.Thread(
            target=self._reminder_worker, daemon=True)
        self._reminder_thread.start()

    def note_foreground(self, launch):
        """
        The shell reports: the person switched to this program
        (`4.0b-A03`, `4.0b-A02`).

        **By default the core still remembers nothing.** The event is
        compared with the waiting reminders and forgotten: not which
        program is in front, nor which was before, nor how long was
        spent in it. Knowing which programs somebody opens is
        information of the same kind as the text of their words
        (`T-19`), and the surest way not to lose such a history is not
        to keep one.

        **A working session is the one case where a history is kept, and
        it takes two switches and an open session to get there**
        (`4.0b-A02`, `T-22`). `watch_apps` lets Rina see the change at
        all — without it this method is never called. `session_apps`
        lets her write it down. And even then nothing accumulates
        unless a session is open, because there is nowhere to put it:
        the chronicle belongs to a named stretch of work, not to the
        program. Turn either switch off, or close the session, and the
        paragraph above is true again word for word.

        **Two fields, not a log.** What is held between events is the
        program in front and the moment it came forward; when the next
        change arrives, the time between them is credited to the one
        that is leaving. A running total per application in the open
        session is a far smaller thing than a list of switches with
        their timestamps, and it answers the only question anybody asked
        of it — "what did this stretch of work go on".

        What arrives is a **path**, not a window name: a person changes the
        window title themselves by opening somebody else's file in an
        editor, and matching on it would mean matching against the contents
        of somebody else's document.
        """
        launch = str(launch or "")
        if not launch:
            return 0
        self._credit_foreground(launch)
        fired = self._reminders.triggered(
            {"kind": "app.foreground", "launch": launch})
        for item in fired:
            self._fire_reminder(item)
        return len(fired)

    def _credit_foreground(self, launch, now=None):
        """
        Give the program that is leaving the time it was in front.

        Held outside the session on purpose. The pair "what is in front
        and since when" exists whether or not anybody is recording, and
        putting it in the store would mean a write on every window
        change — for a person who never switched the recording on.
        """
        import time as _time

        now = now if now is not None else _time.time()
        was, since = self._in_front
        self._in_front = (launch, now)
        if not was or was == launch or not since:
            return
        if not self._settings.get("session_apps", False):
            return
        self._sessions.saw(self._app_name(was), now - since)

    @staticmethod
    def _app_name(launch):
        """
        The program, as a person would name it — not its full path.

        A path names a place on somebody's disk, and a session is read
        back to them out loud. `C:\\Users\\...\\Code.exe` in an answer is
        both unreadable and more than was asked for.
        """
        import os as _os

        base = _os.path.basename(str(launch or "")).strip()
        stem, ext = _os.path.splitext(base)
        return stem or base

    def _fire_reminder(self, item):
        """
        One firing opens a trace chain of its own (4.0-D15).

        Shared by the clock and by the occasion: a firing is a firing, and
        these two paths have no reason to differ. While they did differ,
        what was bound to an event did not reach the journal the way
        everything else did.
        """
        with trace_scope():
            self._reminders.mark_done(item["id"])
            # The snapshot was taken before the mark and still says
            # done: false. Sending it as it is means telling the shell that
            # a reminder fired which by its own words did not: the event
            # would contradict the store, from which the shell will take
            # the list a second later.
            self._emit(Events.REMINDER_FIRED, item={**item, "done": True})

    def _reminder_worker(self):
        """
        The scheduler: once a second it looks whether it is time.

        **Every firing opens a trace chain of its own** (4.0-D15). A reminder
        is called by nobody — it is itself the beginning of an action, and
        everything that follows it (an event to the shell, a spoken phrase,
        journal entries) belongs to one chain. Without this a fired alarm
        would look in the journal like a set of unconnected lines, and there
        would be nothing to work out "why did she start talking at night"
        with.
        """
        store = self._reminders
        while not self._stop_reminders.wait(1.0):
            try:
                for item in store.due():
                    self._fire_reminder(item)
            except Exception:
                pass          # a read failure must not kill the scheduler

    # ------------------------------------------------------------------
    # the wake word
    # ------------------------------------------------------------------
    def _extract_command(self, text, require_wake):
        """
        The command's text without the wake word.
        None means there was no activation and the command must be ignored.
        """
        if not require_wake:
            return text.strip()

        from voice.wake import get_wake_words, strip_wake

        wake_words = get_wake_words(self._settings)
        if not wake_words:
            return text.strip()
        return strip_wake(text, wake_words)

    # ------------------------------------------------------------------
    # clarifying questions and execution
    # ------------------------------------------------------------------
    # What a phrase means is decided by the router (core/router.py).
    # The unclosed question is remembered by the dialogue (core/dialog.py).
    # The doing is done by the executor (core/executor.py).
    # What is left to the core is tying them together and keeping the history.

    def _sync_plugin_tools(self, *_):
        """
        Bring the registry into line with the switched-on plugins (`4.0-H03`).

        Called on every change of the set: switched on — the tools appeared,
        switched off — they vanished. A registry that remembers a
        switched-off plugin's tool will call it one day, and by then the
        plugin is no longer loaded.

        There is deliberately no separate "refresh" here: the only way to
        find out that the registry has drifted from reality is to compare it
        with reality every time.
        """
        if self._plugins is None:
            return

        for plugin_id, loaded in self._plugins.plugins.items():
            prefix = self._plugins.tool_prefix(plugin_id)
            already = [n for n in self._tools.registry.names()
                       if n.startswith(prefix)]

            if not loaded.enabled or loaded.error:
                if already:
                    self._tools.drop_tools(prefix)
                continue

            if already:
                continue                # already created

            for tool, run in self._plugins.declared_tools(plugin_id):
                try:
                    self._tools.add_tool(tool, run)
                except ValueError:
                    # The name is taken: the plugin declared two tools with
                    # one name. Its defect, and it is already in its journal.
                    pass

    def _apps(self):
        """
        The list of programs: the shell's, if there is one, otherwise our own.

        Our own path stays for the sake of the 3.1.0 application, which
        lives in one process and has no shell at all. As soon as 3.1.0 is
        withdrawn, it will go too — along with half of
        `voice/app_index.py`.
        """
        if self.apps_source is None:
            from voice import app_index

            return app_index.cached_index() or []

        if self._apps_cache is None:
            from voice.app_index import AppEntry

            self._apps_cache = [AppEntry.from_dict(item)
                                for item in self.apps_source()]
        return self._apps_cache

    def _router_context(self, source, require_wake):
        """Everything the router needs to know about the world — a snapshot at this moment."""
        from voice import app_index, app_launcher
        from core import llm

        question = self._dialog.current()
        return router_mod.RouterContext(
            apps=self._apps(),
            aliases=dict(self._settings.get("app_aliases", {}) or {}),
            pending=question.to_dict() if question else None,
            wake_words=tuple(get_wake_words(self._settings)),
            # The wake word is not asked for while a conversation is
            # open (`4.0b-E06`): it is said once, and what follows is the
            # same exchange.
            require_wake=require_wake and not self.talking(),
            source=source,
            # Asked of ourselves rather than read off the name of the
            # source: see `RouterContext.unbidden`.
            unbidden=bool(self._always_listen),
            reminders_active=len(self._reminders.active()),
            llm_enabled=llm.is_enabled(),
            web_fallback=bool(self._settings.get("web_search_fallback", True)),
            last_launch_query=self._last_launch_query,
            todo_find=self._todo.matches,
            # Whether a session is open changes what the answer to
            # "finish it" is, and nothing else; the router still
            # decides nothing about sessions it cannot see.
            session_open=self._sessions.current() is not None,
        )

    @property
    def todo(self):
        """The list of things to do (`4.0b-A13`) — for the protocol."""
        return self._todo

    @property
    def sessions(self):
        """Working sessions (`4.0b-A02`) — for the protocol."""
        return self._sessions

    def _remember_choice(self, query, entry):
        from voice import app_launcher

        app_launcher.remember(query, entry.launch, entry.kind, entry.name,
                              settings=self._settings)

    def ask_for(self, prompt, intent, args=None, slot="", options=()):
        """
        Say something and wait for an answer that will be acted on.

        The general shape of Rina asking (`4.0b-E06`): the question
        carries what to do, so a new thing to ask about needs no new
        kind of question. With a `slot` the answer is a value and the
        options are suggestions; without one it is yes or no.
        """
        self.say(prompt)
        self._ask(dialog_mod.Question.asked(prompt, intent, args, slot,
                                            options))

    def offer(self, key, value, about, sentence):
        """
        Say something is now possible, and offer to switch it on.

        Rina's own initiative (`4.0b-E06`), and deliberately the narrowest
        kind of it: what she offers is always one setting taking one
        value, and always something the person has just brought about
        themselves. Nothing new is learned about anybody to make the
        offer — the boundary the plan draws around initiative.

        **Focus holds it back rather than throws it away** (`4.0b-A05`).
        Inside a focused session the offer is kept and made once when
        the session closes. Dropping it would make focus a way of
        losing things: the voice a person waited an hour to download
        would finish, say nothing, and never mention itself again.
        Making it anyway would make the mode a promise Rina breaks.

        One offer is kept, not a queue. Two offers about the same
        setting are the same offer, and a list of everything that
        happened during three hours of work is not an interruption
        avoided — it is an interruption postponed and made worse.
        """
        if self._sessions.focused():
            self._held_offer = (key, value, about, sentence)
            return
        self.say(sentence)
        self._ask(dialog_mod.Question.offer_setting(key, value, about))

    def release_held(self):
        """
        Give back the one thing focus held, and raise its question.

        Returns the sentence rather than saying it. Whoever closed the
        session is about to speak — "session closed, two hours" — and
        an offer said from here would come out **before** that, which
        is the wrong order for something that has been waiting an hour
        already. The caller puts it at the end of its own answer.

        The question itself is raised here, because a pending question
        is the dialogue's and not the caller's.
        """
        held = self._held_offer
        self._held_offer = None
        if held is None:
            return ""
        key, value, about, sentence = held
        self._ask(dialog_mod.Question.offer_setting(key, value, about))
        return sentence

    def _take_offer(self, intent):
        """The person agreed: switch it on and say so."""
        key = str(intent.arg("key") or "")
        value = str(intent.arg("value") or "")
        if not key:
            return
        self._dialog.answered()
        self._settings.set(key, value)
        self._settings.save()
        self._settings_changed()
        self.say(tr("Включила: {about}.", about=intent.arg("about") or key))

    def _hush_previous(self):
        """Stop whatever is being said: something new has been asked."""
        if self.hush_out is None:
            return
        try:
            self.hush_out()
        except Exception:                                # noqa: BLE001
            log.exception("Не удалось оборвать прежнюю реплику")

    def _settings_changed(self):
        """
        The engine has written a setting itself — tell whoever must rebuild.

        The core's voice is rebuilt from the settings, and it is rebuilt
        by whoever serves `settings.set` over the wire. A setting written
        from in here takes a different road and would otherwise apply
        only after the next restart — the very defect `4.0b-V05` was
        about, met through another door.
        """
        if self.settings_changed is None:
            return
        try:
            self.settings_changed()
        except Exception:                                # noqa: BLE001
            log.exception("Не удалось применить изменённую настройку")

    def _ask(self, question):
        """Ask a question and say it out loud."""
        self._dialog.ask(question)
        self._announce_question(question)

    def _announce_question(self, question):
        """Report outwards that a question has been asked (4.0-F11)."""
        if self.on_question is None:
            return
        try:
            self.on_question(question)
        except Exception:                                # noqa: BLE001
            log.exception("Не удалось объявить заданный вопрос")

    def answer_question(self, yes: bool) -> None:
        """
        Answer the question that was asked on the person's behalf.

        **By the same path as by voice.** Consent goes through parsing, as
        if the person had said "yes": it has exactly one road, and a second
        implementation of consent is a second place where a safe action can
        go wrong. The words are taken from the router rather than from the
        interface: this is part of parsing, not a label on a button.
        """
        word = (router_mod.YES_WORDS if yes else router_mod.NO_WORDS)[0]
        self.handle_command_async(word, source="typed")


    def _run_user_command(self, user_cmd):
        """Perform a user command — through the executor."""
        return self._executor.run_user_command(user_cmd)


    def run_command_by_id(self, command_id):
        """
        Perform a command by its id (the "Run" button in the list).

        In the background too: a sequence with pauses takes seconds to
        perform, and the button is pressed from the interface thread.
        """
        for cmd in self._cmd_store.all():
            if cmd.get("id") == command_id:
                self._ensure_command_worker()
                ctx = contextvars.copy_context()
                threading.Thread(
                    target=ctx.run, args=(self._run_user_command, cmd),
                    name="rina-run-command", daemon=True).start()
                return

    def try_command(self, card):
        """
        Try a command being assembled, without saving it (`4.0b-A09`).

        In the background for the same reason as `run_command_by_id`: a
        sequence with pauses takes seconds, and the press comes from the
        interface thread.
        """
        self._ensure_command_worker()
        ctx = contextvars.copy_context()
        threading.Thread(
            target=ctx.run, args=(self._executor.try_user_command, card),
            name="rina-try-command", daemon=True).start()

    # ------------------------------------------------------------------
    # the command queue
    # ------------------------------------------------------------------
    def _ensure_command_worker(self):
        with self._command_lock:
            worker = self._command_worker
            if worker is None or not worker.is_alive():
                self._command_worker = threading.Thread(
                    target=self._command_loop, name="rina-commands",
                    daemon=True)
                self._command_worker.start()

    def _command_loop(self):
        while True:
            text, require_wake, source, done, ctx = self._commands.get()
            try:
                ctx.run(self.handle_command, text,
                        require_wake=require_wake, source=source)
            except Exception as e:
                # without this an exception would carry off the worker, and
                # every following command would stay in the queue forever
                log.exception("Сбой обработки команды")
                try:
                    self.say(tr("Не получилось выполнить команду: ") + str(e),
                             sound="error")
                except Exception:
                    pass
            finally:
                done.set()

    def handle_command_async(self, text, require_wake=False, source="typed",
                             wait=False):
        """
        Put a command into the handling queue.

        The shell calls this instead of handle_command: the pipeline works
        in its own thread, the window stays alive, and the order of commands
        is preserved. wait=True is needed by the "always listen" mode: it
        must not listen further until the previous phrase has been dealt
        with.
        """
        self._ensure_command_worker()
        done = threading.Event()
        # The execution context is put into the queue along with the
        # command. The end-to-end trace (4.0-D15) rides in it: the worker
        # thread is long-lived and serves many commands in a row, so it
        # cannot be tied to one of them — the context belongs to the command,
        # not to the thread.
        #
        # The first run of the two processes showed this outright: Rina's
        # answer arrived with a trace that did not match the request's, and
        # there was nothing to tie request to answer with across two
        # journals.
        self._commands.put((text, require_wake, source, done,
                            contextvars.copy_context()))
        if wait:
            done.wait()
        return done

    # ------------------------------------------------------------------
    # the command pipeline
    # ------------------------------------------------------------------
    def handle_command(self, text, require_wake=False, source="typed"):
        ctx = self._router_context(source, require_wake)
        intent = router_mod.route(text, ctx)

        # The program index may not have been built yet: in 3.1.0 it was
        # built by the very first launch command. We repeat the parse exactly
        # once and only when the index is empty — otherwise the first
        # "louder" would wait for a walk of the disk.
        if intent.name == "app.not_found" and not ctx.apps:
            from voice import app_index

            ctx.apps = app_index.get_index() or []
            if ctx.apps:
                intent = router_mod.route(text, ctx)

        # Written into the open session, if one is open (`4.0b-A02`).
        #
        # **This is the text of a command, which the journal refuses to
        # keep at all** (`T-05`: «текста команды в журнале нет никогда»,
        # even with `log_texts` on). The two are not in conflict, and
        # the difference is worth stating rather than leaving to be
        # noticed. The journal exists to work out what happened after
        # something went wrong, and for that "what was launched" is
        # enough — the words add nothing and cost a recording of
        # somebody's speech. A session exists to answer "what did I do
        # yesterday", and there the words **are** the answer. It is
        # opened by name, read back on request, shown row by row in
        # "what Rina knows about me", and forgotten one session at a
        # time. `T-22`.
        #
        # After the parse rather than before: a phrase that turned out
        # not to be addressed to her is not a command that was given.
        if intent.name != "silence":
            self._sessions.remember_command(text)

        if intent.name == "silence":
            # Said out loud in the journal, because from outside this is
            # the same silence as not hearing at all — and a person met
            # both and could not tell them apart. "Heard, but the name
            # was not in it" and "heard nothing" want opposite fixes: the
            # first is about how one speaks to her, the second about the
            # microphone.
            log.info("Расслышано, но не мне (%s): %s", intent.stage,
                     safe(text))
            return

        # She was spoken to — so the conversation is open, and for the
        # next little while the name need not be said again (`4.0b-E06`).
        # Only for what was said aloud: a typed line needs no wake word
        # anyway, and opening the ear because somebody typed would be
        # answering a question nobody asked.
        if source in ("voice", "always"):
            self._open_talk()

        # **A new command replaces the answer to the old one.**
        #
        # Asked something else, she stops saying the previous thing:
        # finishing an answer nobody is waiting for any more is talking
        # over the person who moved on. Met as a mess — a command said
        # three times because it seemed unheard, three answers, and all
        # of them at once.
        #
        # Here rather than where speech is sent, because the rule is
        # about commands and not about speech: a reminder going off in
        # the middle of an answer waits its turn instead of eating it.
        self._hush_previous()

        if intent.name == "offer.accepted":
            # The "yes" goes into the conversation like any other word.
            # Without it the record reads "Switch it on?" — "Switched
            # on", with nobody having agreed to anything in between.
            self._history.add("user", text, source=source)
            self._emit(Events.HISTORY_CHANGED)
            self._take_offer(intent)
            return

        if intent.name == "ask.wake":
            self._history.add("user", "Рина", source=source)
            self._emit(Events.HISTORY_CHANGED)
            self._executor.execute(intent, source)
            return

        command = intent.text
        log.info("Команда (%s): %s", source, safe(command))
        self._history.add("user", command, source=source)
        self._emit(Events.HISTORY_CHANGED)

        # Remember what was launched, so that a correction has something
        # to attach to (`4.0b-A04`). What is remembered is **the word that
        # was said**, not the program: what has to be learned is how the
        # person names things, and "no, I meant Chrome" refers to the word
        # rather than to what opened.
        #
        # Only a successful launch: there is nothing to correct about "not
        # found" — there it was the search that erred, not the choice.
        #
        # And only for one turn. "Following a launch" means exactly
        # following: without clearing it the memory lived for the whole
        # session, and "no, I meant Chrome" said an hour later silently
        # rewrote a word the person had long stopped talking about. The
        # suite caught this itself — a correction attached to a launch from
        # somebody else's case.
        self._last_launch_query = (intent.arg("query") or ""
                                   if intent.name == "app.launch" else "")

        # The phrase was an answer to the question asked — the router has already worked that out.
        if intent.stage == "pending":
            self._dialog.answered()
            if intent.name == "cancelled":
                security_log().info(
                    "Опасное действие отменено пользователем: %s",
                    intent.arg("action") or "пользовательская команда")
            self._executor.execute(intent, source)
            return

        # Not an answer — the question is withdrawn. That is how 3.1.0
        # behaves: any unrecognised line forgets the question asked
        # (inventory, §6).
        self._dialog.dropped()

        # The router does not yet parse plugins and user commands: a plugin
        # is somebody else's code, and "would it take the phrase" is found
        # out only by running it.
        if self._dispatch_plugin(command):
            return
        if self._dispatch_user_command(command):
            return

        # The language model is the only thing the core does itself: the
        # answer takes seconds, and it cannot be waited for in this thread.
        if intent.name == "llm.answer":
            self._ask_llm_async(command, source)
            return

        # An intent after which we wait for an answer is first performed
        # (the question has to be spoken), and then becomes the question
        # asked. The order matters: the confirmation is issued during
        # execution, and its identifier has to go into the question.
        result = self._executor.execute(intent, source)

        if intent.needs_answer:
            question = self._question_for(intent, result)
            self._dialog.ask(question)
            self._announce_question(question)

    @staticmethod
    def _question_for(intent, result=None):
        """
        An intent awaiting an answer -> a question asked.

        For a dangerous action the confirmation that was issued is put into
        the question: a person's consent applies to a particular call, not
        to the fact that the question was once asked (4.0-C05).
        """
        confirmation_id = ""
        if result is not None:
            confirmation_id = str(result.data.get("confirmation_id", ""))

        if intent.name == "app.ambiguous":
            return Question(kind=dialog_mod.CHOOSE_APP,
                            options=tuple(intent.arg("options") or ()),
                            query=intent.arg("query") or "")
        if intent.name == "music.ask":
            # The suggestions travel with the question; the answer may
            # be neither of them, and then it is taken as said. See
            # `dialog.ASKED`.
            from voice import music

            return Question.asked(intent.text or "", "music.play",
                                  slot="genre", options=music.SUGGESTED)
        if intent.name == "todo.ambiguous":
            return Question(kind=dialog_mod.CHOOSE_TODO,
                            options=tuple(intent.arg("options") or ()),
                            query=intent.arg("query") or "")
        if intent.name == "system.confirm":
            return Question.confirm_action(intent.arg("action"),
                                           confirmation_id)
        return Question.confirm_command(intent.arg("command_id") or "",
                                        confirmation_id)

    def _dispatch_plugin(self, command):
        if self._plugins is None:
            return False
        try:
            if self._plugins.dispatch_command(command):
                log.debug("Команду обработал плагин")
                return True
        except Exception:
            # a plugin is somebody else's code; its failure must not tear
            # the pipeline, but must not vanish without trace either
            log.exception("Сбой плагина при разборе команды")
        return False

    def _dispatch_user_command(self, command):
        from voice.user_commands import matches, command_needs_confirm

        try:
            for user_cmd in self._cmd_store.all():
                if not matches(user_cmd, command):
                    continue
                if command_needs_confirm(user_cmd):
                    self._ask(Question.confirm_command(user_cmd.get("id")))
                    self.say(tr("Команда «{name}» выключит или перезагрузит "
                                "компьютер. Точно выполнить?",
                                name=(user_cmd.get("triggers") or ["?"])[0]))
                else:
                    self._executor.run_user_command(user_cmd)
                return True
        except Exception:
            log.exception("Сбой при разборе пользовательских команд")
        return False


    def _ask_llm_async(self, command, source):
        """
        Asks the model in the background and answers when it answers.

        Through the registry rather than directly: going to the model is a
        network call with the `network.local` permission, and it is obliged
        to land in the call journal along with the rest (4.0-C06, C07).
        """
        def worker():
            self._emit(Events.THINKING, active=True)
            try:
                result = self._tools.call(
                    "ask_model",
                    {"question": command, "context": self._history.all()},
                    source=source)
            finally:
                self._emit(Events.THINKING, active=False)

            if result.ok and result.message:
                self.say(result.message)
                return
            # the model did not answer — we behave as if it were not there
            self._fallback_reply(command, source)

        threading.Thread(target=worker, daemon=True).start()

    def _fallback_reply(self, command, source):
        """
        The fallback — a search on the internet.

        With the microphone open on her own initiative we do not search:
        noise and chance speech land here, and a browser must not be
        opened on them. Asked of the mode, not of the name of the source —
        that name is `voice` in both modes, and the rule had never fired.
        """
        allowed = (self._settings.get("web_search_fallback", True)
                   and not self._always_listen)
        if allowed:
            result = self._tools.call("web_search", {"query": command},
                                      source=source)
            if result.ok:
                # The wording differs from an explicit search: the person
                # did not ask to search, and it is more honest to say so.
                self.say(tr("Не нашла такой команды — поищу «{query}» "
                            "в интернете.", query=command))
                return

        self.say(tr("Извини, я не поняла команду."), sound="error")

    # ------------------------------------------------------------------
    # settings that depend on the language and the microphone
    # ------------------------------------------------------------------
    def listen_seconds(self):
        try:
            value = int(self._settings.get("listen_seconds", 8))
        except (TypeError, ValueError):
            return 8
        # The floor is in the schema now, where it can be read back; this
        # only guards a profile written before that.
        return max(3, min(60, value))

    def lang_code(self):
        """The recognition language = the interface language (one setting)."""
        lang_map = {"Русский": "ru", "English": "en", "Українська": "uk",
                    "Español": "es", "Deutsch": "de"}
        return lang_map.get(self._settings.get("ui_language", "Русский"), "ru")

    def shutdown(self):
        self._stop_always.set()
        self._stop_reminders.set()
