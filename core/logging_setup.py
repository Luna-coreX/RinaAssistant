"""
Журналирование приложения.

Зачем это появилось: оба аудита 3.0.0 воспроизводили проблемы в песочнице,
потому что журналов не существовало вовсе. Сбой в фоновом потоке уносил поток
молча, и снаружи было видно только, что «ничего не произошло». После
разделения на два процесса (4.0.0) отладка вслепую станет невозможной.

Приватность. Тексты реплик — это содержимое разговора, и в журнал они не
попадают. Исключение одно: уровень DEBUG при явно включённой настройке
`log_texts`. Во всех остальных случаях вместо текста пишется его длина, чего
достаточно, чтобы отличить «пустой ввод» от «10 000 символов», и недостаточно,
чтобы прочитать разговор. Поэтому журнал можно прикладывать к сообщению об
ошибке, не разглашая переписку.

Qt здесь нет намеренно: модуль лежит в ядре и должен работать в headless-режиме.
"""

import logging
import logging.handlers
import os
import sys
import threading


LOGGER_NAME = "rina"
FILE_NAME = "rina.log"

# Отдельный файл под события, которые оба аудита 3.0.0 искали руками:
# установка и замена плагинов, отклонённые имена, импорт команд, запуск
# системных утилит, нелокальный адрес модели, отказ от опасного действия.
# Он короткий и его не нужно вычитывать из общего потока, а уровень
# приложения на него не влияет — такие записи нужны всегда.
SECURITY_LOGGER_NAME = "rina.security"
SECURITY_FILE_NAME = "security.log"

# Журнал нужен для разбора последнего сбоя, а не для истории за месяц:
# 1 МБ на файл и три ротации — это заведомо больше одного сеанса.
MAX_BYTES = 1024 * 1024
BACKUP_COUNT = 3

LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")
DEFAULT_LEVEL = "INFO"
_LEVEL_VALUES = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
}

_FORMAT = "%(asctime)s %(levelname)-7s %(name)-20s %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_lock = threading.Lock()
_configured = False
_hooks_installed = False


# ---------------------------------------------------------------------------
# Расположение
# ---------------------------------------------------------------------------
def logs_dir() -> str:
    """Папка с журналами рядом с настройками. Создаётся при обращении."""
    from core.settings_store import config_dir

    path = os.path.join(config_dir(), "logs")
    os.makedirs(path, exist_ok=True)
    return path


def log_path() -> str:
    return os.path.join(logs_dir(), FILE_NAME)


def security_log() -> logging.Logger:
    """
    Журнал безопасности. Пишет и в свой файл, и в общий (через родителя),
    чтобы в общем журнале сохранялась связная хронология.
    """
    return logging.getLogger(SECURITY_LOGGER_NAME)


def get_logger(name: str = "") -> logging.Logger:
    """Логгер приложения. `name` — короткое имя подсистемы («engine», «tts»)."""
    return logging.getLogger(f"{LOGGER_NAME}.{name}" if name else LOGGER_NAME)


# ---------------------------------------------------------------------------
# Настройки
# ---------------------------------------------------------------------------
def _settings():
    from core.settings_store import settings
    return settings


def current_level() -> int:
    """Уровень из настроек. До их загрузки — значение по умолчанию."""
    try:
        name = str(_settings().get("log_level", DEFAULT_LEVEL)).upper()
    except Exception:
        name = DEFAULT_LEVEL
    return _LEVEL_VALUES.get(name, logging.INFO)


def texts_allowed() -> bool:
    """Разрешил ли пользователь писать в журнал содержимое реплик."""
    try:
        return bool(_settings().get("log_texts", False))
    except Exception:
        return False


def safe(text) -> str:
    """
    Реплика в виде, пригодном для журнала.

    Сам текст — только с явного разрешения; иначе длина, по которой видно
    форму проблемы, но не её содержание.
    """
    text = "" if text is None else str(text)
    if texts_allowed():
        return repr(text)
    return f"<{len(text)} симв.>"


# ---------------------------------------------------------------------------
# Настройка
# ---------------------------------------------------------------------------
def setup(force: bool = False) -> None:
    """
    Поднимает журналирование. Безопасно вызывать до загрузки настроек:
    уровень тогда берётся по умолчанию, а `apply_settings()` поправит его.
    """
    global _configured

    with _lock:
        if _configured and not force:
            return

        logger = logging.getLogger(LOGGER_NAME)
        # пропускаем всё, отбор делают обработчики — иначе смена уровня
        # в настройках потребовала бы пересборки логгера
        logger.setLevel(logging.DEBUG)
        logger.propagate = False

        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            try:
                handler.close()
            except Exception:
                pass

        formatter = logging.Formatter(_FORMAT, datefmt=_DATE_FORMAT)

        try:
            file_handler = logging.handlers.RotatingFileHandler(
                log_path(), maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT,
                encoding="utf-8")
            file_handler.setFormatter(formatter)
            file_handler.setLevel(current_level())
            logger.addHandler(file_handler)
        except OSError:
            # без журнала жить можно, без приложения — нет
            pass

        # В собранном exe stderr может отсутствовать, а при запуске из
        # исходников он полезен: предупреждения видно сразу.
        if getattr(sys, "stderr", None) is not None:
            stream_handler = logging.StreamHandler(sys.stderr)
            stream_handler.setFormatter(formatter)
            stream_handler.setLevel(logging.WARNING)
            logger.addHandler(stream_handler)

        _setup_security_handler(formatter)
        _install_excepthooks()
        _configured = True


def _setup_security_handler(formatter):
    """Свой файл для журнала безопасности, независимо от общего уровня."""
    security = logging.getLogger(SECURITY_LOGGER_NAME)
    security.setLevel(logging.INFO)
    for handler in list(security.handlers):
        security.removeHandler(handler)
        try:
            handler.close()
        except Exception:
            pass
    try:
        handler = logging.handlers.RotatingFileHandler(
            os.path.join(logs_dir(), SECURITY_FILE_NAME),
            maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8")
        handler.setFormatter(formatter)
        handler.setLevel(logging.INFO)
        security.addHandler(handler)
    except OSError:
        pass


def apply_settings() -> None:
    """Перечитать уровень из настроек — после их загрузки или изменения."""
    level = current_level()
    for handler in logging.getLogger(LOGGER_NAME).handlers:
        if isinstance(handler, logging.handlers.RotatingFileHandler):
            handler.setLevel(level)


def log_startup(version: str = "") -> None:
    """Первая запись сеанса: по ней в присланном журнале видно окружение."""
    log = get_logger("app")
    log.info("--- запуск Rina Assistant %s ---", version or "?")
    log.info("Python %s, платформа %s",
             sys.version.split()[0], sys.platform)
    log.info("Данные: %s", os.path.dirname(log_path()))
    security_log().info("--- начало сеанса ---")
    if texts_allowed():
        log.warning("Включена запись текстов реплик в журнал (log_texts)")


# ---------------------------------------------------------------------------
# Необработанные исключения
# ---------------------------------------------------------------------------
def _install_excepthooks() -> None:
    global _hooks_installed
    if _hooks_installed:
        return

    log = get_logger("crash")

    previous = sys.excepthook

    def main_hook(exc_type, exc_value, traceback_obj):
        if not issubclass(exc_type, KeyboardInterrupt):
            log.critical("Необработанное исключение",
                         exc_info=(exc_type, exc_value, traceback_obj))
        # Штатный обработчик печатает то же самое в stderr, куда уже пишет
        # наш обработчик, — получалась бы двойная трассировка. Чужой
        # обработчик, наоборот, вызываем: он мог быть поставлен не нами.
        if previous is not sys.__excepthook__:
            previous(exc_type, exc_value, traceback_obj)

    sys.excepthook = main_hook

    # Исключение в фоновом потоке уносит поток молча: пользователь видит,
    # что действие просто не произошло. Так терялся сбой распознавания.
    previous_thread = getattr(threading, "excepthook", None)
    if previous_thread is not None:
        def thread_hook(args):
            if not issubclass(args.exc_type, SystemExit):
                name = args.thread.name if args.thread is not None else "?"
                log.error("Исключение в потоке %s", name,
                          exc_info=(args.exc_type, args.exc_value,
                                    args.exc_traceback))
            if previous_thread is not getattr(threading, "__excepthook__", None):
                previous_thread(args)

        threading.excepthook = thread_hook

    _hooks_installed = True
