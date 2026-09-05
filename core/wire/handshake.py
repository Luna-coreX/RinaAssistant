"""
The handshake, versions and capabilities.

Plan item `4.0-D03`; specification, §4.

The handshake solves two problems that are easy to confuse.

**The protocol version** answers the question "do we understand each other
at all". Each side declares a **set** of versions rather than one, and they
work over the greatest common one. A set — because ADR 0004 obliges the
shell to keep the previous version for one release: it declares `[1, 2]` and
works the same with a new core and with an old one. With a single number a
staged upgrade is impossible — both processes would have to be updated at
once, and they are released separately.

**Capabilities** answer the question "of what is understood, what can the
correspondent do". A capability is a promise to understand a group of
methods. A side does not call a method whose capability the correspondent
has not declared, and so a new shell with an old core does not break but
simply does not show what the old core cannot do.

**The capability catalogue is kept here, and that is an addition to the
specification.** In §4 the lists of capabilities are given as an example
("capabilities": [...]); there is no complete list tied to methods there.
Without one the implementation would have kept a private dictionary, and the
promise that "the specification was written before the implementation" would
become untrue at the sides' first divergence. The table below was entered
into §4 of the specification by the same change as this module.
"""

import uuid
from dataclasses import dataclass, field

from core.wire.errors import (ERROR_INCOMPATIBLE, ERROR_NOT_READY,
                              ERROR_UNKNOWN_METHOD, fault)


class Side:
    SHELL = "shell"
    CORE = "core"


class SessionState:
    NOT_READY = "not_ready"
    READY = "ready"
    CLOSED = "closed"


@dataclass(frozen=True)
class Capability:
    """
    A promise to understand a group of methods.

    `methods` is sometimes empty: a capability may unlock nothing and only
    report. `llm` is exactly such a one: it has no method of its own, but
    the shell decides by it whether to show the language model's settings at
    all.
    """

    name: str
    side: str
    methods: tuple[str, ...] = ()
    note: str = ""


#: Methods available without a declared capability: without them a session is meaningless.
BASE_METHODS = (
    # The handshake is a method too, and its absence from this list was a
    # gap: the check "every method is described in the specification" did
    # not see it, and the shell could not name it other than as a quoted
    # string. Found while building the C# side, which does not write names
    # but takes them from a snapshot of the contract.
    "hello",
    "command.handle",
    "command.run_by_id",
    "settings.describe",
    "settings.options",
    "settings.reset",
    "hotkeys.actions",
    "settings.get",
    "settings.set",
    "core.shutdown",
    "ping",
    "pong",
    # Stream control is basic, whereas the kind of stream is unlocked by a
    # capability: the method always exists, but `audio.input` cannot be
    # opened on a correspondent without a microphone. See
    # core/wire/data.py::KINDS.
    "stream.open",
    "stream.close",
    "stream.credit",
)

_CAPABILITY_LIST = (
    # --- declared by the shell ---
    Capability("audio.input", Side.SHELL, (),
               "микрофон есть; поток открывается stream.open (4.0-D07)"),
    Capability("audio.output", Side.SHELL, (),
               "воспроизведение есть; поток открывается stream.open"),
    Capability("permissions", Side.SHELL, ("permission.request",),
               "оболочка умеет спросить человека (§11)"),
    Capability("window.actions", Side.SHELL, (),
               "оболочка исполняет window.action; событие, а не метод"),
    Capability("apps", Side.SHELL, ("apps.index", "apps.launch"),
               "индекс программ и запуск живут в оболочке (4.0-G06)"),
    Capability("system", Side.SHELL, ("system.do",),
               "громкость, медиа, питание, снимок экрана (4.0-G01..G03)"),
    # --- declared by the core ---
    Capability("stt", Side.CORE,
               ("speech.listen_once", "speech.set_always_listen"),
               "распознавание речи"),
    Capability("tts", Side.CORE, ("speech.say", "speech.test"),
               "синтез речи"),
    Capability("reminders", Side.CORE, ("reminders.list", "reminders.cancel", "reminders.create"),
               "таймеры и будильники живут в ядре (4.0-E05)"),
    Capability("plugins", Side.CORE,
               ("plugins.list", "plugins.set_enabled", "plugins.page",
                "plugins.action", "plugins.install"),
               "плагины"),
    # User commands and history. Introduced in 4.0-F04: the surface
    # inventory demands them, and there were no methods at all — the shell
    # could neither show the list of commands nor clear the history. The
    # boundary rule forbids losing capabilities, and without these methods
    # six would have been lost.
    Capability("commands", Side.CORE,
               ("commands.list", "commands.kinds", "commands.builtin",
                "commands.save", "commands.delete",
                "commands.set_enabled", "commands.export",
                "commands.import"),
               "свои команды пользователя"),
    Capability("history", Side.CORE,
               ("history.list", "history.clear", "history.export"),
               "разговор: посмотреть, стереть, выгрузить"),
    Capability("llm", Side.CORE, (),
               "ядро умеет отвечать моделью; отдельного метода нет"),
    Capability("tasks", Side.CORE, ("task.cancel",),
               "долгие задачи с прогрессом и отменой (4.0-D09, D10)"),
    # --- declared by nobody in 4.0 (§12) ---
    Capability("actuation", Side.CORE,
               ("actuation.session.begin", "actuation.session.end",
                "actuation.input.click", "actuation.input.type",
                "actuation.input.key", "actuation.screen.capture",
                "window.list", "window.focus"),
               "синтез ввода и захват экрана; реализация в 5.0, "
               "в 4.0 методы отвечают protocol.unknown_method"),
)

CAPABILITIES = {c.name: c for c in _CAPABILITY_LIST}

#: What each side declares in 4.0. `actuation` is declared by nobody — which
#: is exactly why its methods answer "unknown method" rather than "no
#: permission": in 4.0 they do not exist rather than being forbidden.
SHELL_CAPABILITIES = tuple(c.name for c in _CAPABILITY_LIST
                           if c.side == Side.SHELL)
CORE_CAPABILITIES = tuple(c.name for c in _CAPABILITY_LIST
                          if c.side == Side.CORE and c.name != "actuation")

_METHOD_TO_CAPABILITY = {
    method: cap.name
    for cap in _CAPABILITY_LIST
    for method in cap.methods
}


def capability_of(method: str) -> str | None:
    """Which capability unlocks a method. `None` means the method is basic."""
    if method in BASE_METHODS:
        return None
    return _METHOD_TO_CAPABILITY.get(method, _UNKNOWN)


#: Different from `None`: `None` means "a basic method", this means "there is no such thing".
_UNKNOWN = "?"


def negotiate(local: list[int], remote: list[int]) -> int:
    """
    The greatest common protocol version.

    Incompatibility is obliged to be intelligible (§15.3): not a
    disconnection but a message naming both sides. A shell that declared
    `[1, 2]` is obliged to work with a core that declared `[1]` — that is a
    requirement of §15.3a, and without it ADR 0004's commitment to keep the
    previous version stays decorative.
    """
    if not local or not remote:
        raise fault(ERROR_INCOMPATIBLE,
                    "сторона не объявила ни одной версии протокола",
                    local=list(local), remote=list(remote))
    common = sorted(set(local) & set(remote))
    if not common:
        raise fault(
            ERROR_INCOMPATIBLE,
            "Общей версии протокола нет: здесь понимают "
            f"{_versions(local)}, у собеседника {_versions(remote)}. "
            "Обновите ту сторону, что старее.",
            local=sorted(local), remote=sorted(remote))
    return common[-1]


def _versions(values) -> str:
    return ", ".join(str(v) for v in sorted(values))


@dataclass
class Session:
    """
    The state of one session on one side.

    Until the handshake succeeds, any method except `hello` answers
    `protocol.not_ready` (§4). This is no formality: without a version it is
    unknown how to read a message, and without capabilities, whether it
    could have been sent at all.
    """

    side: str
    versions: list[int] = field(default_factory=lambda: [1])
    capabilities: tuple[str, ...] = ()
    app_version: str = "4.0.0"
    #: The version of the data format on disk (ADR 0004). The core takes it
    #: from the store; the shell receives it in the handshake and shows it.
    data_version: int = 0
    locale: str = "ru"

    state: str = SessionState.NOT_READY
    version: int | None = None
    peer_capabilities: tuple[str, ...] = ()
    #: What the correspondent said about its data.
    peer_data_version: int = 0
    peer_version: str = ""
    session_id: str = ""

    def __post_init__(self):
        if self.side not in (Side.SHELL, Side.CORE):
            raise ValueError(f"неизвестная сторона: {self.side!r}")
        if not self.capabilities:
            self.capabilities = (SHELL_CAPABILITIES if self.side == Side.SHELL
                                 else CORE_CAPABILITIES)
        for name in self.capabilities:
            if name not in CAPABILITIES:
                raise ValueError(f"неизвестная возможность: {name!r}")
            if CAPABILITIES[name].side != self.side:
                raise ValueError(
                    f"возможность {name!r} объявляет другая сторона")

    # -- the handshake --------------------------------------------------------

    def hello_payload(self) -> dict:
        """Shell to core: the session's first message (§4)."""
        return {
            "protocol_versions": sorted(self.versions),
            "shell_version": self.app_version,
            "capabilities": list(self.capabilities),
            "locale": self.locale,
        }

    def handle_hello(self, payload: dict) -> dict:
        """
        The core accepts `hello` and answers.

        The version is chosen here and named in the answer: from then on it
        is that one which stands in every message's `v` field, and the
        question is not asked a second time.
        """
        remote = payload.get("protocol_versions")
        if not isinstance(remote, list) or not all(
                isinstance(v, int) and not isinstance(v, bool) for v in remote):
            raise fault(
                ERROR_INCOMPATIBLE,
                "в рукопожатии нет списка версий протокола",
                got=remote)

        self.version = negotiate(self.versions, remote)
        self.peer_capabilities = tuple(payload.get("capabilities") or ())
        self.peer_version = str(payload.get("shell_version") or "")
        self.locale = str(payload.get("locale") or self.locale)
        self.session_id = uuid.uuid4().hex
        self.state = SessionState.READY
        return {
            "protocol_versions": sorted(self.versions),
            "protocol_version": self.version,
            "core_version": self.app_version,
            # The fourth version from ADR 0004: the data schema on disk.
            # Here rather than in `settings.get`: `config_version` is secret
            # — it is the state of the store, not a setting. But a rollback
            # is limited by precisely this one, and a person has to be told
            # what it is.
            "data_version": self.data_version,
            "capabilities": list(self.capabilities),
            "session_id": self.session_id,
        }

    def accept_hello_result(self, payload: dict) -> int:
        """The shell accepts the core's answer and moves into the working state."""
        chosen = payload.get("protocol_version")
        if isinstance(chosen, bool) or not isinstance(chosen, int):
            raise fault(ERROR_INCOMPATIBLE,
                        "ядро не назвало выбранную версию протокола",
                        got=chosen)
        if chosen not in self.versions:
            raise fault(
                ERROR_INCOMPATIBLE,
                f"ядро выбрало версию {chosen}, которой здесь нет "
                f"(объявлено: {_versions(self.versions)}).",
                chosen=chosen, local=sorted(self.versions))
        self.version = chosen
        self.peer_capabilities = tuple(payload.get("capabilities") or ())
        self.peer_version = str(payload.get("core_version") or "")
        self.peer_data_version = int(payload.get("data_version") or 0)
        self.session_id = str(payload.get("session_id") or "")
        self.state = SessionState.READY
        return chosen

    # -- the guards -----------------------------------------------------------

    @property
    def ready(self) -> bool:
        return self.state == SessionState.READY

    def may_call(self, method: str) -> bool:
        """Whether this method may be called: the correspondent declared its capability."""
        if not self.ready:
            return False
        cap = capability_of(method)
        if cap is None:
            return True
        if cap is _UNKNOWN:
            return False
        return cap in self.peer_capabilities

    def check_outgoing(self, method: str) -> None:
        """
        Before sending a request. Silent if the call is allowed.

        A check on our own side, not only on the other one: the
        correspondent will answer with an error anyway, but then we learn of
        the defect from another process's journal — the most expensive way
        of learning about one's own mistakes.
        """
        if not self.ready:
            raise fault(ERROR_NOT_READY,
                        "рукопожатие ещё не состоялось",
                        method=method)
        cap = capability_of(method)
        if cap is _UNKNOWN:
            raise fault(ERROR_UNKNOWN_METHOD,
                        f"метод {method!r} протоколу неизвестен",
                        method=method)
        if cap is not None and cap not in self.peer_capabilities:
            raise fault(
                ERROR_UNKNOWN_METHOD,
                f"собеседник не объявил возможность {cap!r}, "
                f"метод {method!r} звать нельзя",
                method=method, capability=cap)

    def check_incoming(self, method: str) -> None:
        """
        Before handling an incoming request.

        An unknown method and a method of an undeclared capability give one
        and the same answer — `protocol.unknown_method`. This is not
        carelessness: to the correspondent there is no difference. The
        actuation methods (§12) exist in the specification, but neither side
        declares `actuation` in 4.0, and so they answer "unknown method"
        rather than "no permission": in 4.0 they do not exist.
        """
        if not self.ready and method != "hello":
            raise fault(
                ERROR_NOT_READY,
                "до рукопожатия принимается только hello",
                method=method)
        if method == "hello":
            return
        cap = capability_of(method)
        if cap is _UNKNOWN:
            raise fault(ERROR_UNKNOWN_METHOD,
                        f"метод {method!r} протоколу неизвестен",
                        method=method)
        if cap is not None and cap not in self.capabilities:
            raise fault(
                ERROR_UNKNOWN_METHOD,
                f"метод {method!r} здесь не поддерживается",
                method=method, capability=cap)

    def close(self) -> None:
        self.state = SessionState.CLOSED
        self.version = None
        self.peer_capabilities = ()
