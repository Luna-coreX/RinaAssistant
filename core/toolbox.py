"""
The catalogue of Rina's tools — descriptions, not implementation.

Plan item 4.0-C03, the first half: declare everything the core can do as
registry descriptions. The second half — putting execution through the
registry — lives in core/executor.py.

The list is derived from the inventory of behaviour
(docs/INVENTORY-3.1.0.md, §3 "Side effects"): here is exactly what Rina
changes the world with, and nothing beyond. These two documents are worth
reading side by side — they describe one and the same thing from different
sides, and a divergence between them means one of them is out of date.

The permissions are laid out not "just in case" but by what a tool actually
does. `calculate` requires nothing: it computes an expression and goes
nowhere. `ask_model` requires the network, and which network depends on a
setting: a local address and somebody else's server are different things,
and pretending they are one permission would be untrue.

There is no Qt here: the module lies in the core.
"""

from core.tools import Param, Tool, ToolRegistry


# ---------------------------------------------------------------------------
# Programs
# ---------------------------------------------------------------------------
LAUNCH_APP = Tool(
    name="launch_app",
    summary="Запустить установленную программу по её имени в индексе.",
    params=(
        Param("name", "string",
              "Отображаемое имя программы, как оно записано в индексе."),
        Param("query", "string",
              "Что пользователь сказал — чтобы запомнить выбор.",
              required=False),
    ),
    permissions={"process.launch"},
    # Launching is not idempotent: a second call opens a second window.
    idempotent=False,
    returns="Подтверждение запуска с именем программы.",
    errors=("app.not_found", "app.launch_failed"),
)

LIST_APPS = Tool(
    name="list_apps",
    summary="Найденные на компьютере программы.",
    params=(
        Param("query", "string", "Отбор по имени; пусто — весь список.",
              required=False),
        Param("limit", "integer", "Сколько вернуть.", required=False,
              minimum=1, maximum=200, default=20),
    ),
    permissions=set(),          # reading the index changes nothing
    idempotent=True,
    returns="Список программ: имя, источник, вид.",
    errors=(),
)


# ---------------------------------------------------------------------------
# The system
# ---------------------------------------------------------------------------
SET_VOLUME = Tool(
    name="set_volume",
    summary="Прибавить, убавить или переключить звук.",
    params=(
        Param("action", "string", "Что сделать с громкостью.",
              choices=("up", "down", "mute")),
    ),
    permissions={"system.media"},
    idempotent=False,           # "louder" twice is two steps of volume
    returns="Короткое подтверждение.",
    errors=("internal",),
)

MEDIA_CONTROL = Tool(
    name="media_control",
    summary="Управление воспроизведением: следующий, предыдущий, пауза.",
    params=(
        Param("action", "string", "Действие плеера.",
              choices=("next", "previous", "play_pause")),
    ),
    permissions={"system.media"},
    idempotent=False,
    returns="Короткое подтверждение.",
    errors=("internal",),
)

LOCK_SCREEN = Tool(
    name="lock_screen",
    summary="Заблокировать рабочий стол.",
    params=(),
    permissions={"system.lock"},
    idempotent=True,            # locking what is locked is harmless
    returns="Подтверждение.",
    errors=("internal",),
)

POWER_ACTION = Tool(
    name="power_action",
    summary="Выключить, перезагрузить или усыпить компьютер.",
    params=(
        Param("action", "string", "Что сделать с питанием.",
              choices=("shutdown", "restart", "sleep")),
    ),
    permissions={"system.power"},
    # Not "confirmation is desirable" but "it cannot be performed without
    # confirmation": otherwise one misrecognised phrase shuts the computer
    # down.
    confirm_required=True,
    idempotent=False,
    returns="Подтверждение начала действия.",
    errors=("confirmation.required", "confirmation.invalid", "internal"),
)

TAKE_SCREENSHOT = Tool(
    name="take_screenshot",
    summary="Снять экран и сохранить снимок в «Изображения».",
    params=(),
    permissions={"screen.capture"},
    idempotent=False,           # every call creates a new file
    returns="Путь к сохранённому файлу.",
    errors=("internal",),
)


# ---------------------------------------------------------------------------
# Reminders
# ---------------------------------------------------------------------------
CREATE_REMINDER = Tool(
    name="create_reminder",
    summary="Поставить таймер, напоминание или будильник.",
    params=(
        Param("kind", "string", "Вид записи.",
              choices=("timer", "reminder", "alarm")),
        Param("seconds", "integer", "Через сколько секунд сработает.",
              required=False, minimum=1, maximum=315360000),
        Param("at", "number", "Точный момент срабатывания, секунды с эпохи.",
              required=False),
        Param("text", "string", "О чём напомнить.", required=False),
    ),
    permissions=set(),
    idempotent=False,           # two calls, two reminders
    returns="Подтверждение со сроком или временем.",
    errors=("tool.invalid_arguments",),
)

LIST_REMINDERS = Tool(
    name="list_reminders",
    summary="Что сейчас запланировано.",
    params=(),
    permissions=set(),
    idempotent=True,
    returns="Список активных записей.",
    errors=(),
)

CANCEL_REMINDER = Tool(
    name="cancel_reminder",
    summary="Отменить одну запись или все сразу.",
    params=(
        Param("id", "string", "Что отменить; пусто — отменить всё.",
              required=False),
    ),
    permissions=set(),
    # Cancelling what is cancelled is harmless and gives the same result.
    idempotent=True,
    returns="Сколько записей снято.",
    errors=(),
)


# ---------------------------------------------------------------------------
# User commands and plugins
# ---------------------------------------------------------------------------
RUN_USER_COMMAND = Tool(
    name="run_user_command",
    summary="Выполнить команду, заведённую пользователем.",
    params=(
        Param("command_id", "string", "Идентификатор команды."),
    ),
    # A command may launch programs and open sites; a narrower permission
    # cannot be given without knowing its contents.
    permissions={"process.launch", "network.external"},
    idempotent=False,
    returns="Ответ, заданный командой, либо подтверждение по умолчанию.",
    errors=("internal",),
)

DISPATCH_PLUGIN_COMMAND = Tool(
    name="dispatch_plugin_command",
    summary="Передать фразу плагинам.",
    params=(
        Param("text", "string", "Фраза целиком."),
    ),
    # A plugin today is arbitrary code in the core's process, and it has no
    # honest set of permissions. Isolation is 4.0-H07; until then the entry
    # here means "a plugin can do everything the application can", and that
    # is written down in SECURITY.md rather than hidden.
    permissions={"process.launch", "network.external", "files.read"},
    idempotent=False,
    returns="Признак того, что плагин взял фразу.",
    errors=("internal",),
)


# ---------------------------------------------------------------------------
# Answers
# ---------------------------------------------------------------------------
CALCULATE = Tool(
    name="calculate",
    summary="Посчитать арифметическое выражение.",
    params=(
        Param("expression", "string", "Выражение или фраза со счётом."),
    ),
    permissions=set(),          # computes and nothing more
    idempotent=True,
    returns="Результат вычисления.",
    errors=("tool.invalid_arguments",),
)

WEB_SEARCH = Tool(
    name="web_search",
    summary="Открыть поиск в браузере.",
    params=(
        Param("query", "string", "Что искать."),
        Param("engine", "string", "Поисковая система.", required=False,
              choices=("google", "yandex", "duckduckgo", "bing")),
    ),
    permissions={"network.external"},
    idempotent=True,            # the same query gives the same page
    returns="Подтверждение с запросом и системой.",
    errors=("internal",),
)

ASK_MODEL = Tool(
    name="ask_model",
    summary="Задать вопрос языковой модели.",
    params=(
        Param("question", "string", "Вопрос."),
        Param("context", "array", "Последние реплики для связности.",
              required=False),
    ),
    # The local network by default. If the address in the settings is not
    # local, the executor is obliged to demand network.external as well: "a
    # model on one's own computer" and "a model on somebody else's server"
    # are different promises.
    permissions={"network.local"},
    idempotent=False,           # the model answers the same thing differently
    returns="Ответ модели одной-двумя фразами.",
    errors=("llm.unavailable",),
)


ALL_TOOLS = (
    LAUNCH_APP, LIST_APPS,
    SET_VOLUME, MEDIA_CONTROL, LOCK_SCREEN, POWER_ACTION, TAKE_SCREENSHOT,
    CREATE_REMINDER, LIST_REMINDERS, CANCEL_REMINDER,
    RUN_USER_COMMAND, DISPATCH_PLUGIN_COMMAND,
    CALCULATE, WEB_SEARCH, ASK_MODEL,
)


def default_registry():
    """A registry with every one of the application's tools."""
    return ToolRegistry(ALL_TOOLS)
