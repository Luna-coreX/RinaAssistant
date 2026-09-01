"""
Каталог инструментов Рины — описания, а не реализация.

Задача плана 4.0-C03, первая половина: объявить всё, что ядро умеет делать,
в виде описаний реестра. Вторая половина — провести исполнение через реестр —
живёт в core/executor.py.

Список выведен из инвентаря поведения (docs/INVENTORY-3.1.0.md, §3
«Побочные эффекты»): здесь ровно то, чем Рина меняет мир, и ничего сверх.
Читать эти два документа стоит рядом — они описывают одно и то же с разных
сторон, и расхождение между ними означает, что один из них устарел.

Разрешения расставлены не «на всякий случай», а по тому, что инструмент
действительно делает. `calculate` не требует ничего: он считает выражение и
никуда не ходит. `ask_model` требует сети, и какой именно — зависит от
настройки: локальный адрес и чужой сервер это разные вещи, и притворяться,
что это одно разрешение, было бы неправдой.

Qt здесь нет: модуль лежит в ядре.
"""

from core.tools import Param, Tool, ToolRegistry


# ---------------------------------------------------------------------------
# Программы
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
    # Запуск не идемпотентен: второй вызов откроет второе окно.
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
    permissions=set(),          # чтение индекса ничего не меняет
    idempotent=True,
    returns="Список программ: имя, источник, вид.",
    errors=(),
)


# ---------------------------------------------------------------------------
# Система
# ---------------------------------------------------------------------------
SET_VOLUME = Tool(
    name="set_volume",
    summary="Прибавить, убавить или переключить звук.",
    params=(
        Param("action", "string", "Что сделать с громкостью.",
              choices=("up", "down", "mute")),
    ),
    permissions={"system.media"},
    idempotent=False,           # «громче» дважды — это два шага громкости
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
    idempotent=True,            # заблокировать заблокированное безвредно
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
    # Не «желательно подтвердить», а нельзя выполнить без подтверждения:
    # одна неверно распознанная фраза иначе выключает компьютер.
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
    idempotent=False,           # каждый вызов создаёт новый файл
    returns="Путь к сохранённому файлу.",
    errors=("internal",),
)


# ---------------------------------------------------------------------------
# Напоминания
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
    idempotent=False,           # два вызова — два напоминания
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
    # Отменить отменённое — безвредно и даёт тот же результат.
    idempotent=True,
    returns="Сколько записей снято.",
    errors=(),
)


# ---------------------------------------------------------------------------
# Пользовательские команды и плагины
# ---------------------------------------------------------------------------
RUN_USER_COMMAND = Tool(
    name="run_user_command",
    summary="Выполнить команду, заведённую пользователем.",
    params=(
        Param("command_id", "string", "Идентификатор команды."),
    ),
    # Команда может запускать программы и открывать сайты; более узкого
    # разрешения дать нельзя, не зная её содержимого.
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
    # Плагин сегодня — произвольный код в процессе ядра, и честного набора
    # разрешений у него нет. Изоляция — 4.0-H07; до неё запись здесь
    # означает «плагин может всё, что может приложение», и это записано
    # в SECURITY.md, а не спрятано.
    permissions={"process.launch", "network.external", "files.read"},
    idempotent=False,
    returns="Признак того, что плагин взял фразу.",
    errors=("internal",),
)


# ---------------------------------------------------------------------------
# Ответы
# ---------------------------------------------------------------------------
CALCULATE = Tool(
    name="calculate",
    summary="Посчитать арифметическое выражение.",
    params=(
        Param("expression", "string", "Выражение или фраза со счётом."),
    ),
    permissions=set(),          # считает и ничего больше
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
    idempotent=True,            # тот же запрос даёт ту же страницу
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
    # Локальная сеть — по умолчанию. Если адрес в настройках не локальный,
    # исполнитель обязан потребовать ещё и network.external: «модель на
    # своём компьютере» и «модель на чужом сервере» — разные обещания.
    permissions={"network.local"},
    idempotent=False,           # модель отвечает по-разному на одно и то же
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
    """Реестр со всеми инструментами приложения."""
    return ToolRegistry(ALL_TOOLS)
