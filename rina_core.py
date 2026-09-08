# -*- coding: utf-8 -*-
"""
The core's entry point: Rina with no window.

Plan item 4.0-E01.

Until now the core was a library that `main.py` raised together with the
window. Here it becomes a process with a life of its own: arguments, a
journal, a channel to the shell and an orderly shutdown.

To run (usually the shell does this, 4.0-E07):

    python rina_core.py --transport pipe --session 3f0c1a2b
    python rina_core.py --transport stdio          # debugging by hand

**Qt is not imported.** This is not a wish but a checkable property: a
core that has dragged in the interface library will stop starting where
that library is absent, and the split will exist only on paper. Checked
right here, at startup.

**Who outlives whom.** The shell starts the core and holds the channel; a
core that sees the channel break shuts down (§13 of the specification).
There is deliberately no "sleep mode": a core that outlived its shell is a
process nobody will close and that is holding the microphone.

Exit codes:

    0   finished normally: asked to, or the shell went away
    2   the arguments could not be parsed
    3   the channel did not open
"""

import argparse
import os
import signal
import sys
import threading

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

EXIT_OK = 0
EXIT_ARGS = 2
EXIT_TRANSPORT = 3


def parse_args(argv):
    parser = argparse.ArgumentParser(
        prog="rina_core",
        description="Ядро Рины как отдельный процесс.")
    parser.add_argument(
        "--transport", choices=("pipe", "stdio"), default="pipe",
        help="pipe — именованный канал от оболочки (ADR 0002); "
             "stdio — отладка руками, канала данных нет")
    parser.add_argument(
        "--session", default="",
        help="идентификатор сессии; из него складываются имена каналов")
    parser.add_argument(
        "--log-level", choices=("DEBUG", "INFO", "WARNING", "ERROR"),
        default=None, help="перекрыть уровень журнала на этот запуск")
    parser.add_argument(
        "--connect-timeout", type=float, default=10.0,
        help="сколько ждать, пока оболочка поднимет канал")
    parser.add_argument(
        "--print-capabilities", action="store_true",
        help="напечатать возможности и версии протокола и выйти")
    parser.add_argument(
        "--list-backups", action="store_true",
        help="показать копии, снятые перед миграциями, и выйти")
    parser.add_argument(
        "--restore-backup", nargs="?", const=-1, type=int, default=None,
        metavar="ВЕРСИЯ",
        help="вернуть настройки, команды, плагины, историю и напоминания "
             "из копии (по умолчанию — из самой свежей) и выйти")
    return parser.parse_args(argv)


def stop_plugins(plugins):
    """
    Stop the plugin processes.

    A plugin is our child process, and leaving one behind means leaving a
    python in the system that does nothing and obeys nobody. The same rule
    by which the core does not outlive the shell.
    """
    try:
        plugins.stop_all()
    except Exception:                                    # noqa: BLE001
        log.exception("Плагины не остановились")


def check_headless():
    """
    Make sure the interface library has not been dragged in.

    The check stands before the core is created: if Qt arrives
    transitively, this is where we have to find out, not on a machine
    where it is absent.
    """
    if "PySide6" in sys.modules:
        raise RuntimeError(
            "в ядро затянулся PySide6 — разделение нарушено: "
            "ядро обязано работать там, где интерфейсной библиотеки нет")


def manage_backups(args):
    """
    List the backups, or go back to one of them.

    Both halves of `4.0-I02` in one place: the backup is taken before a
    migration by itself, and the person restores it — so they have to be
    told what there is. A rollback that cannot be called is not the
    ability to roll back.
    """
    from core.settings_store import config_dir, settings

    available = settings.backups()
    if args.list_backups:
        print(f"каталог данных: {config_dir()}")
        if not available:
            print("копий нет: миграции ещё не было")
        for version in available:
            print(f"  backup-v{version} — снята перед переходом с версии "
                  f"формата {version}")
        return EXIT_OK

    if not available:
        print("возвращаться некуда: копий нет", file=sys.stderr)
        return EXIT_ARGS

    wanted = None if args.restore_backup == -1 else args.restore_backup
    if wanted is not None and wanted not in available:
        print(f"копии backup-v{wanted} нет; есть: "
              + ", ".join(f"v{v}" for v in available), file=sys.stderr)
        return EXIT_ARGS

    if not settings.restore_backup(wanted):
        print("вернуть не вышло — смотрите журнал", file=sys.stderr)
        return EXIT_ARGS

    took = available[-1] if wanted is None else wanted
    print(f"вернули из backup-v{took}")
    # What was displaced has not been erased, and that has to be said:
    # otherwise a person who rolled back by mistake will think they lost
    # everything accumulated since the migration.
    print(f"то, что заменили, отложено в "
          f"{os.path.join(config_dir(), f'backup-v{took}', 'replaced')}")
    return EXIT_OK


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    try:
        args = parse_args(argv)
    except SystemExit as exc:
        return EXIT_ARGS if exc.code else EXIT_OK

    from core import logging_setup
    logging_setup.setup()
    if args.log_level:
        import logging
        for handler in logging.getLogger(logging_setup.LOGGER_NAME).handlers:
            handler.setLevel(getattr(logging, args.log_level))
    log = logging_setup.get_logger("core")

    from core.wire.handshake import CORE_CAPABILITIES
    if args.print_capabilities:
        print("protocol_versions: 1")
        print("capabilities: " + ", ".join(CORE_CAPABILITIES))
        return EXIT_OK

    # Backups and rollback come before everything else: a migration has a
    # second half (`4.0-I02`), and without a way to call it the backup
    # stays a folder taking up space. Here rather than in the window: one
    # rolls back once, and usually exactly when the window will not
    # open.
    if args.list_backups or args.restore_backup is not None:
        return manage_backups(args)

    if args.transport == "pipe" and not args.session:
        print("режиму pipe нужен --session", file=sys.stderr)
        return EXIT_ARGS

    check_headless()

    from core.engine import RinaEngine
    from core.events import EventBus
    from core.wire.server import ProtocolServer
    from core.wire.transport import TransportClosed, open_channels

    from version import APP_VERSION
    log.info("Ядро запускается: транспорт %s, сессия %s, версия %s",
             args.transport, args.session or "—", APP_VERSION)

    try:
        channels = open_channels(args.transport, args.session)
        if args.transport == "stdio":
            # A stray print() in any module would spoil a frame in the
            # middle of its length. The transport has already taken the
            # binary buffer, so sys.stdout itself can be pointed at the
            # error stream: printing stays visible but does not reach the
            # wire.
            sys.stdout = sys.stderr
    except (TransportClosed, ValueError) as exc:
        log.error("Канал не открылся: %s", exc)
        print(f"канал не открылся: {exc}", file=sys.stderr)
        return EXIT_TRANSPORT

    # The settings are read before everything else, and out loud: the
    # recognition engine, the voice and the scheduler all look at them.
    # The store would read itself on first access anyway, but then there
    # would not be a line in the journal about where the values came from
    # — and that is the first question when the program behaves
    # differently from how it is set up.
    from core.settings_store import settings as settings_store
    settings_store.load()
    log.info("Настройки прочитаны: %s", settings_store.path)

    # The language of Rina's lines (4.0-F08). The shell translates the
    # interface's words, but what Rina says is her own speech, and the
    # core sets its language. This used to be done by the 3.1.0 window,
    # the program's only entrance; a split program has two entrances, and
    # the core is obliged to manage on its own.
    from core import i18n
    i18n.set_language(str(settings_store.get("ui_language", "Русский")))
    log.info("Язык реплик: %s", i18n.get_language())

    # Plugins belong to the core: they answer commands, and commands are
    # handled by the core. But they live **in processes of their own**
    # (4.0-H07): otherwise a plugin that went into an endless loop would
    # take the core's thread with it, and Rina would fall silent entirely
    # because of somebody else's code. `HostedPlugins` has the same
    # surface as the in-process manager — the core does not need to know
    # where a plugin lives.
    from core.plugin_host import HostedPlugins
    from core.settings_store import settings as core_settings

    plugins = HostedPlugins(settings=core_settings)
    try:
        plugins.discover()
    except Exception:                                    # noqa: BLE001
        # A broken plugin catalogue is no reason not to start the assistant.
        log.exception("Плагины не собрались")

    engine = RinaEngine(plugin_manager=plugins, event_bus=EventBus())
    server = ProtocolServer(engine, channels, app_version=APP_VERSION)

    # Timers live in the core (4.0-E05). The scheduler used to be started
    # by the window; in a split program that is doubly wrong: a reminder
    # set by voice must fire regardless of whether the window is open, and
    # the shell is entitled to be closed into the tray.
    engine.start_reminders()

    # Signals: shut down properly rather than fall over. SIGTERM comes
    # from the shell when stopping, SIGINT from a person at the console;
    # for the core there is no difference, and they are handled alike.
    stopping = threading.Event()

    def on_signal(signum, _frame):
        if not stopping.is_set():
            stopping.set()
            log.info("Сигнал %s: завершаемся", signum)
            server.stop(f"сигнал {signum}")
            channels.close()

    for name in ("SIGINT", "SIGTERM", "SIGBREAK"):
        number = getattr(signal, name, None)
        if number is not None:
            try:
                signal.signal(number, on_signal)
            except (ValueError, OSError):
                pass          # not the main thread, or no such signal here

    try:
        why = server.serve_forever()
    finally:
        # The order matters: release the volatile state first (§13), then
        # shut the core down. The other way round means clearing
        # permissions on an executor that has already been taken apart.
        dropped = server.on_disconnect()
        try:
            engine.shutdown()
        except Exception:                                  # noqa: BLE001
            log.exception("Ядро завершилось с ошибкой")
        # The plugin processes are our children: leaving them behind
        # means leaving a python in the system that does nothing and obeys
        # nobody (4.0-H07).
        stop_plugins(plugins)
        channels.close()

    log.info("Ядро остановлено: %s. Сброшено при обрыве: %s", why, dropped)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
