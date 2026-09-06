"""
The application's journalling.

Why this appeared: both 3.0.0 audits reproduced problems in a sandbox,
because journals did not exist at all. A failure in a background thread
carried the thread off in silence, and from outside all one could see was
that "nothing happened". After the split into two processes (4.0.0),
debugging blind will become impossible.

Privacy. The text of lines is the content of a conversation, and it does not
get into the journal. There is one exception: DEBUG level with the
`log_texts` setting explicitly on. In every other case the text's length is
written instead, which is enough to tell "empty input" from "10,000
characters" and not enough to read the conversation. So the journal can be
attached to a bug report without disclosing the correspondence.

There is deliberately no Qt here: the module lies in the core and must work
headless.
"""

import logging
import logging.handlers
import os
import sys
import threading

from core.trace import TraceFilter


LOGGER_NAME = "rina"
FILE_NAME = "rina.log"

# A separate file for the events that both 3.0.0 audits hunted for by hand:
# installing and replacing plugins, rejected names, importing commands,
# running system utilities, a non-local model address, refusing a dangerous
# action. It is short and need not be read out of the general stream, and the
# application's level does not affect it — such entries are always needed.
SECURITY_LOGGER_NAME = "rina.security"
SECURITY_FILE_NAME = "security.log"

# The journal is for looking into the last failure, not for a month's
# history: 1 MB per file and three rotations is knowingly more than one
# session.
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

# `trace` is an action's end-to-end identifier (4.0-D15, §14 of the
# specification). It is in the format because a journal without it is
# useless in a two-process system: two programs write two unconnected sets
# of lines, and the question "what happened after that keypress" is answered
# by comparing timestamps, that is, by guesswork. The field is filled in by
# `core.trace.TraceFilter`; the same place explains why a dash is more honest
# than an invented value.
_FORMAT = "%(asctime)s %(levelname)-7s %(trace)-14s %(name)-20s %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_lock = threading.Lock()
_configured = False
_hooks_installed = False


# ---------------------------------------------------------------------------
# Location
# ---------------------------------------------------------------------------
def logs_dir() -> str:
    """The folder with the journals, next to the settings. Created on demand."""
    from core.settings_store import config_dir

    path = os.path.join(config_dir(), "logs")
    os.makedirs(path, exist_ok=True)
    return path


def log_path() -> str:
    return os.path.join(logs_dir(), FILE_NAME)


def security_log() -> logging.Logger:
    """
    The security journal. Writes both to its own file and to the general one
    (through its parent), so that the general journal keeps a coherent
    chronology.
    """
    return logging.getLogger(SECURITY_LOGGER_NAME)


def get_logger(name: str = "") -> logging.Logger:
    """The application's logger. `name` is a subsystem's short name ("engine", "tts")."""
    return logging.getLogger(f"{LOGGER_NAME}.{name}" if name else LOGGER_NAME)


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
def _settings():
    from core.settings_store import settings
    return settings


def current_level() -> int:
    """The level from the settings. Before they are loaded, the default."""
    try:
        name = str(_settings().get("log_level", DEFAULT_LEVEL)).upper()
    except Exception:
        name = DEFAULT_LEVEL
    return _LEVEL_VALUES.get(name, logging.INFO)


def texts_allowed() -> bool:
    """Whether the user allowed the content of lines to be written to the journal."""
    try:
        return bool(_settings().get("log_texts", False))
    except Exception:
        return False


def safe(text) -> str:
    """
    A line in a form fit for the journal.

    The text itself only with explicit permission; otherwise the length, by
    which the shape of a problem is visible but not its content.
    """
    text = "" if text is None else str(text)
    if texts_allowed():
        return repr(text)
    return f"<{len(text)} симв.>"


# ---------------------------------------------------------------------------
# Setting up
# ---------------------------------------------------------------------------
def setup(force: bool = False) -> None:
    """
    Raises journalling. Safe to call before the settings are loaded: the
    level is then taken from the default, and `apply_settings()` will
    correct it.
    """
    global _configured

    with _lock:
        if _configured and not force:
            return

        logger = logging.getLogger(LOGGER_NAME)
        # we let everything through, the handlers do the selecting —
        # otherwise changing the level in the settings would require
        # rebuilding the logger
        logger.setLevel(logging.DEBUG)
        logger.propagate = False

        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            try:
                handler.close()
            except Exception:
                pass

        formatter = logging.Formatter(_FORMAT, datefmt=_DATE_FORMAT)
        # The filter is hung on the handlers rather than on the logger: that
        # way the field also reaches a record created around our paths, and
        # the format does not fall over with a KeyError in the middle of
        # looking into a failure — exactly when the journal is needed most.
        trace_filter = TraceFilter()

        try:
            file_handler = logging.handlers.RotatingFileHandler(
                log_path(), maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT,
                encoding="utf-8")
            file_handler.setFormatter(formatter)
            file_handler.addFilter(trace_filter)
            file_handler.setLevel(current_level())
            logger.addHandler(file_handler)
        except OSError:
            # one can live without a journal, but not without the application
            pass

        # In a built exe stderr may be absent, while when running from
        # source it is useful: warnings are visible at once.
        if getattr(sys, "stderr", None) is not None:
            stream_handler = logging.StreamHandler(sys.stderr)
            stream_handler.setFormatter(formatter)
            stream_handler.addFilter(trace_filter)
            stream_handler.setLevel(logging.WARNING)
            logger.addHandler(stream_handler)

        _setup_security_handler(formatter, trace_filter)
        _install_excepthooks()
        _configured = True


def _setup_security_handler(formatter, trace_filter=None):
    """A file of its own for the security journal, independent of the general level."""
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
        if trace_filter is not None:
            handler.addFilter(trace_filter)
        handler.setLevel(logging.INFO)
        security.addHandler(handler)
    except OSError:
        pass


def apply_settings() -> None:
    """Re-read the level from the settings — after they are loaded or changed."""
    level = current_level()
    for handler in logging.getLogger(LOGGER_NAME).handlers:
        if isinstance(handler, logging.handlers.RotatingFileHandler):
            handler.setLevel(level)


def log_startup(version: str = "") -> None:
    """The session's first entry: by it the environment is visible in a journal that was sent in."""
    log = get_logger("app")
    log.info("--- запуск Rina Assistant %s ---", version or "?")
    log.info("Python %s, платформа %s",
             sys.version.split()[0], sys.platform)
    log.info("Данные: %s", os.path.dirname(log_path()))
    security_log().info("--- начало сеанса ---")
    if texts_allowed():
        log.warning("Включена запись текстов реплик в журнал (log_texts)")


# ---------------------------------------------------------------------------
# Unhandled exceptions
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
        # The standard handler prints the same thing to stderr, where our
        # handler already writes — there would be a double traceback.
        # Somebody else's handler, on the contrary, we do call: it may have
        # been installed by someone other than us.
        if previous is not sys.__excepthook__:
            previous(exc_type, exc_value, traceback_obj)

    sys.excepthook = main_hook

    # An exception in a background thread carries the thread off in silence:
    # the user sees that the action simply did not happen. That is how a
    # recognition failure went missing.
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
