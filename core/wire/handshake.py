"""
Рукопожатие, версии и возможности.

Задача плана `4.0-D03`; спецификация, §4.

Рукопожатие решает две задачи, которые легко перепутать.

**Версия протокола** отвечает на вопрос «понимаем ли мы вообще друг друга».
Каждая сторона объявляет **набор** версий, а не одну, и работают по
наибольшей общей. Набор — потому что ADR 0004 обязывает оболочку держать
предыдущую версию один выпуск: она объявляет `[1, 2]` и одинаково работает и
с новым ядром, и со старым. С одним числом ступенчатое обновление невозможно
— пришлось бы обновлять оба процесса одновременно, а они выпускаются порознь.

**Возможности** отвечают на вопрос «что из понятного собеседник умеет».
Возможность — обещание понимать группу методов. Сторона не вызывает метод,
чью возможность собеседник не объявил, и потому новая оболочка со старым
ядром не ломается, а просто не показывает того, чего старое ядро не умеет.

**Каталог возможностей заведён здесь, и это добавление к спецификации.**
В §4 списки возможностей приведены примером («capabilities»: [...]), полного
перечня с привязкой к методам там нет. Без него реализация завела бы частный
словарь, и обещание «спецификация написана до реализации» стало бы
неправдой при первом же расхождении сторон. Таблица ниже внесена в §4
спецификации тем же изменением, что и этот модуль.
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
    Обещание понимать группу методов.

    `methods` бывает пустым: возможность может ничего не отпирать, а только
    сообщать. `llm` — именно такая: отдельного метода у неё нет, но по ней
    оболочка решает, показывать ли настройки языковой модели вообще.
    """

    name: str
    side: str
    methods: tuple[str, ...] = ()
    note: str = ""


#: Методы, доступные без объявленной возможности: без них сессия бессмысленна.
BASE_METHODS = (
    # Рукопожатие — тоже метод, и его отсутствие в этом перечне было
    # пробелом: сверка «каждый метод описан в спецификации» его не видела,
    # а оболочка не могла назвать его иначе как строкой в кавычках.
    # Обнаружилось при сборке C#-стороны, которая имена не пишет, а берёт
    # из снимка контракта.
    "hello",
    "command.handle",
    "command.run_by_id",
    "settings.describe",
    "settings.options",
    "settings.get",
    "settings.set",
    "core.shutdown",
    "ping",
    "pong",
    # Управление потоками — базовое, а вот вид потока отпирается
    # возможностью: метод существует всегда, но открыть `audio.input` у
    # собеседника без микрофона нельзя. См. core/wire/data.py::KINDS.
    "stream.open",
    "stream.close",
    "stream.credit",
)

_CAPABILITY_LIST = (
    # --- объявляет оболочка ---
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
    # --- объявляет ядро ---
    Capability("stt", Side.CORE,
               ("speech.listen_once", "speech.set_always_listen"),
               "распознавание речи"),
    Capability("tts", Side.CORE, ("speech.say",), "синтез речи"),
    Capability("reminders", Side.CORE, ("reminders.list", "reminders.cancel"),
               "таймеры и будильники живут в ядре (4.0-E05)"),
    Capability("plugins", Side.CORE,
               ("plugins.list", "plugins.set_enabled", "plugins.page",
                "plugins.action", "plugins.install"),
               "плагины"),
    # Пользовательские команды и история. Заведены в 4.0-F04: инвентарь
    # поверхности требует их, а методов не было вовсе — оболочка не могла
    # ни показать список команд, ни очистить историю. Правило рубежа
    # запрещает терять возможности, и без этих методов терялись бы шесть.
    Capability("commands", Side.CORE,
               ("commands.list", "commands.save", "commands.delete",
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
    # --- не объявляется никем в 4.0 (§12) ---
    Capability("actuation", Side.CORE,
               ("actuation.session.begin", "actuation.session.end",
                "actuation.input.click", "actuation.input.type",
                "actuation.input.key", "actuation.screen.capture",
                "window.list", "window.focus"),
               "синтез ввода и захват экрана; реализация в 5.0, "
               "в 4.0 методы отвечают protocol.unknown_method"),
)

CAPABILITIES = {c.name: c for c in _CAPABILITY_LIST}

#: Что объявляет каждая сторона в 4.0. `actuation` не объявляет никто —
#: именно поэтому её методы отвечают «неизвестный метод», а не «нет права»:
#: в 4.0 их не существует, а не запрещено.
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
    """Какая возможность отпирает метод. `None` — метод базовый."""
    if method in BASE_METHODS:
        return None
    return _METHOD_TO_CAPABILITY.get(method, _UNKNOWN)


#: Отличается от `None`: `None` значит «базовый метод», это — «нет такого».
_UNKNOWN = "?"


def negotiate(local: list[int], remote: list[int]) -> int:
    """
    Наибольшая общая версия протокола.

    Несовместимость обязана быть внятной (§15.3): не обрыв, а сообщение,
    называющее обе стороны. Оболочка, объявившая `[1, 2]`, обязана работать с
    ядром, объявившим `[1]`, — это требование §15.3a, и без него обязательство
    ADR 0004 держать предыдущую версию остаётся декоративным.
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
    Состояние одной сессии на одной стороне.

    До успешного рукопожатия любой метод, кроме `hello`, отвечает
    `protocol.not_ready` (§4). Это не формальность: без версии неизвестно, как
    читать сообщение, а без возможностей — можно ли вообще было его слать.
    """

    side: str
    versions: list[int] = field(default_factory=lambda: [1])
    capabilities: tuple[str, ...] = ()
    app_version: str = "4.0.0"
    locale: str = "ru"

    state: str = SessionState.NOT_READY
    version: int | None = None
    peer_capabilities: tuple[str, ...] = ()
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

    # -- рукопожатие ---------------------------------------------------------

    def hello_payload(self) -> dict:
        """Оболочка → ядро: первое сообщение сессии (§4)."""
        return {
            "protocol_versions": sorted(self.versions),
            "shell_version": self.app_version,
            "capabilities": list(self.capabilities),
            "locale": self.locale,
        }

    def handle_hello(self, payload: dict) -> dict:
        """
        Ядро принимает `hello` и отвечает.

        Версия выбирается здесь и называется в ответе: дальше именно она стоит
        в поле `v` каждого сообщения, и второй раз этот вопрос не задаётся.
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
            "capabilities": list(self.capabilities),
            "session_id": self.session_id,
        }

    def accept_hello_result(self, payload: dict) -> int:
        """Оболочка принимает ответ ядра и переходит в рабочее состояние."""
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
        self.session_id = str(payload.get("session_id") or "")
        self.state = SessionState.READY
        return chosen

    # -- сторожа -------------------------------------------------------------

    @property
    def ready(self) -> bool:
        return self.state == SessionState.READY

    def may_call(self, method: str) -> bool:
        """Можно ли звать этот метод: собеседник объявил его возможность."""
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
        Перед отправкой запроса. Молчит, если звать можно.

        Проверка на своей стороне, а не только на чужой: собеседник и так
        ответит ошибкой, но тогда о дефекте узнают из журнала другого
        процесса — самый дорогой способ узнавать о своих ошибках.
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
        Перед обработкой пришедшего запроса.

        Неизвестный метод и метод необъявленной возможности дают один и тот же
        ответ — `protocol.unknown_method`. Это не небрежность: для собеседника
        разницы нет. Методы актуации (§12) существуют в спецификации, но ни
        одна сторона не объявляет `actuation` в 4.0, и потому они отвечают
        «неизвестный метод», а не «нет права»: в 4.0 их не существует.
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
