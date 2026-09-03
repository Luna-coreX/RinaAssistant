# -*- coding: utf-8 -*-
"""
Точка входа ядра: Рина без окна.

Задача плана 4.0-E01.

До сих пор ядро было библиотекой, которую поднимал `main.py` вместе с окном.
Здесь оно становится процессом, у которого своя жизнь: аргументы, журнал,
канал к оболочке и корректное завершение.

Запуск (обычно это делает оболочка, 4.0-E07):

    python rina_core.py --transport pipe --session 3f0c1a2b
    python rina_core.py --transport stdio          # отладка руками

**Qt не импортируется.** Это не пожелание, а проверяемое свойство: ядро,
затянувшее интерфейсную библиотеку, перестанет запускаться там, где её нет, и
разделение окажется на бумаге. Проверяется прямо здесь, при старте.

**Кто кого переживает.** Оболочка запускает ядро и держит канал; ядро,
увидевшее обрыв, завершается (§13 спецификации). Отдельного «спящего режима»
нет намеренно: ядро, пережившее свою оболочку, — это процесс, который никто
не закроет и который держит микрофон.

Коды возврата:

    0   завершились нормально: попросили или оболочка ушла
    2   аргументы не разобраны
    3   канал не открылся
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
    return parser.parse_args(argv)


def stop_plugins(plugins):
    """
    Остановить процессы плагинов.

    Плагин — наш дочерний процесс, и оставить его после себя значит
    оставить в системе python, который ничего не делает и никому не
    подчиняется. То же правило, по которому ядро не переживает оболочку.
    """
    try:
        plugins.stop_all()
    except Exception:                                    # noqa: BLE001
        log.exception("Плагины не остановились")


def check_headless():
    """
    Убедиться, что интерфейсная библиотека не затянулась.

    Проверка стоит до создания ядра: если Qt приедет транзитивно, узнать об
    этом надо здесь, а не на машине, где его нет.
    """
    if "PySide6" in sys.modules:
        raise RuntimeError(
            "в ядро затянулся PySide6 — разделение нарушено: "
            "ядро обязано работать там, где интерфейсной библиотеки нет")


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
            # Случайный print() в любом модуле испортил бы кадр посреди
            # длины. Транспорт уже забрал двоичный буфер, поэтому сам
            # sys.stdout можно увести в поток ошибок: печать останется
            # видимой, но в провод не попадёт.
            sys.stdout = sys.stderr
    except (TransportClosed, ValueError) as exc:
        log.error("Канал не открылся: %s", exc)
        print(f"канал не открылся: {exc}", file=sys.stderr)
        return EXIT_TRANSPORT

    # Настройки читаются до всего остального и вслух: на них смотрят и
    # движок распознавания, и голос, и планировщик. Хранилище прочитает
    # себя и само при первом обращении, но тогда в журнале не будет ни
    # строки о том, откуда взялись значения, — а это первый вопрос, когда
    # программа ведёт себя не так, как настроена.
    from core.settings_store import settings as settings_store
    settings_store.load()
    log.info("Настройки прочитаны: %s", settings_store.path)

    # Язык реплик Рины (4.0-F08). Слова интерфейса переводит оболочка, но
    # то, что Рина говорит, — её собственная речь, и язык ей задаёт ядро.
    # Раньше это делало окно 3.1.0, единственный вход в программу; в
    # разделённой программе входов два, и ядро обязано уметь само.
    from core import i18n
    i18n.set_language(str(settings_store.get("ui_language", "Русский")))
    log.info("Язык реплик: %s", i18n.get_language())

    # Плагины принадлежат ядру: они отвечают на команды, а команды
    # обрабатывает ядро. Но живут они **в своих процессах** (4.0-H07):
    # плагин, ушедший в бесконечный цикл, иначе забирал бы поток ядра, и
    # Рина замолкала бы целиком из-за чужого кода. Поверхность у
    # `HostedPlugins` та же, что у менеджера в процессе, — ядру не нужно
    # знать, где живёт плагин.
    from core.plugin_host import HostedPlugins
    from core.settings_store import settings as core_settings

    plugins = HostedPlugins(settings=core_settings)
    try:
        plugins.discover()
    except Exception:                                    # noqa: BLE001
        # Битый каталог плагинов не повод не запускать помощника.
        log.exception("Плагины не собрались")

    engine = RinaEngine(plugin_manager=plugins, event_bus=EventBus())
    server = ProtocolServer(engine, channels, app_version=APP_VERSION)

    # Таймеры живут в ядре (4.0-E05). Раньше планировщик запускало окно; в
    # разделённой программе это неверно вдвойне: напоминание, поставленное
    # голосом, обязано сработать независимо от того, открыто ли окно, а
    # оболочка вправе быть закрытой в трей.
    engine.start_reminders()

    # Сигналы: завершаться корректно, а не падать. SIGTERM приходит от
    # оболочки при остановке, SIGINT — от человека в консоли; для ядра
    # разницы нет, и обрабатываются они одинаково.
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
                pass          # не главный поток или сигнала нет на платформе

    try:
        why = server.serve_forever()
    finally:
        # Порядок важен: сначала отпустить летучее состояние (§13), потом
        # гасить ядро. Наоборот — значит сбрасывать разрешения у уже
        # разобранного исполнителя.
        dropped = server.on_disconnect()
        try:
            engine.shutdown()
        except Exception:                                  # noqa: BLE001
            log.exception("Ядро завершилось с ошибкой")
        # Процессы плагинов — наши дочерние: оставить их после себя значит
        # оставить в системе python, который ничего не делает и никому не
        # подчиняется (4.0-H07).
        stop_plugins(plugins)
        channels.close()

    log.info("Ядро остановлено: %s. Сброшено при обрыве: %s", why, dropped)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
