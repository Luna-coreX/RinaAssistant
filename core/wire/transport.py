"""
Транспорт: как байты попадают на ту сторону.

Задача плана `4.0-E01`; решение о транспорте — [ADR 0002](../../docs/adr/0002-ipc-transport.md).

Протокол от транспорта не зависит — это записано в ADR 0002 и проверяется
conformance-набором, который гоняет тот же контракт через транспорт внутри
процесса. Здесь собраны реализации, и все они умеют ровно три вещи: отдать
байты, принять байты, закрыться.

**Именованный канал держит оболочка, ядро подключается клиентом.** Инверсия
привычной раскладки, и она же снимает зависимость: в Python клиент — это
обычный `open(r'\\\\.\\pipe\\...', 'r+b')`, тогда как сервер потребовал бы
`pywin32` или Proactor-цикл.

**Режим `stdio` — ответ на единственную цену того решения.** ADR 0002 честно
записал, что у канала нет ни `netstat`, ни перехвата пакетов, и отверг
отладочный режим по TCP: порт без проверки подлинности, который однажды
забудут выключить. У стандартного ввода-вывода этого недостатка нет — он не
слушающая точка, к нему нельзя подключиться снаружи, он живёт ровно столько,
сколько живёт запущенный процесс. Отладка получается, дыры не появляется.
"""

import os
import queue
import sys
import threading


class TransportClosed(Exception):
    """Та сторона закрылась. Для ядра это значит «оболочки больше нет»."""


class Transport:
    """Один поток байтов в обе стороны."""

    def send(self, data: bytes) -> None:
        raise NotImplementedError

    def recv(self, max_bytes: int = 65536) -> bytes:
        """
        Прочитать сколько есть.

        Пустые байты значат «сейчас ничего нет», а не «всё кончилось».
        Конец потока — это `TransportClosed`, и говорит о нём сам транспорт:
        у канала пустое чтение означает закрытие, у очереди внутри процесса —
        что сообщение ещё не положили. Сервер, догадывающийся об этом по виду
        объекта, ошибётся на первом же новом транспорте — и ошибётся молча,
        крутя пустой цикл вместо завершения.
        """
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError


class Channels:
    """
    Пара каналов сессии: управляющий и данных.

    Данных может не быть — например, в режиме `stdio`, где поток один. Это
    не поломка: канал данных нужен звуку, а отлаживают обычно команды.
    Отсутствие выражено явно, чтобы попытка открыть поток упиралась в
    внятный отказ, а не в `None` посреди отправки.
    """

    def __init__(self, control: Transport, data: Transport | None = None):
        self.control = control
        self.data = data

    def close(self) -> None:
        for channel in (self.control, self.data):
            if channel is not None:
                try:
                    channel.close()
                except Exception:
                    pass


class InProcessTransport(Transport):
    """
    Транспорт внутри процесса: для тестов и conformance.

    Существует не ради удобства тестов, а потому что этого требует ADR 0002:
    протокол, который нельзя прогнать мимо канала, от канала зависит — просто
    об этом ещё не знают.
    """

    def __init__(self):
        self._inbox: queue.Queue = queue.Queue()
        self.peer: "InProcessTransport | None" = None
        self._closed = False

    @staticmethod
    def pair() -> tuple["InProcessTransport", "InProcessTransport"]:
        left, right = InProcessTransport(), InProcessTransport()
        left.peer, right.peer = right, left
        return left, right

    def send(self, data: bytes) -> None:
        if self._closed or self.peer is None:
            raise TransportClosed("транспорт закрыт")
        self.peer._inbox.put(bytes(data))

    def recv(self, max_bytes: int = 65536) -> bytes:
        if self._closed and self._inbox.empty():
            raise TransportClosed("транспорт закрыт")
        try:
            return self._inbox.get(timeout=0.05)
        except queue.Empty:
            if self._closed:
                raise TransportClosed("транспорт закрыт") from None
            return b""

    def close(self) -> None:
        self._closed = True
        if self.peer is not None and not self.peer._closed:
            self.peer._closed = True


class StdioTransport(Transport):
    """
    Управляющий канал по стандартному вводу-выводу.

    Двоичные потоки, а не текстовые: кадр несёт четыре байта длины, и
    текстовая обёртка с переводом строк испортила бы их молча.
    """

    def __init__(self, stdin=None, stdout=None):
        self._in = stdin if stdin is not None else sys.stdin.buffer
        self._out = stdout if stdout is not None else sys.stdout.buffer
        self._lock = threading.Lock()

    def send(self, data: bytes) -> None:
        with self._lock:
            self._out.write(data)
            self._out.flush()

    def recv(self, max_bytes: int = 65536) -> bytes:
        chunk = self._in.read1(max_bytes) if hasattr(self._in, "read1") \
            else self._in.read(max_bytes)
        if not chunk:
            # На стандартном вводе пустое чтение бывает только одно — конец.
            raise TransportClosed("стандартный ввод закрыт")
        return chunk

    def close(self) -> None:
        try:
            self._out.flush()
        except Exception:
            pass


class PipeClientTransport(Transport):
    """
    Клиент именованного канала Windows.

    Ядро подключается, а не слушает: сервером канала работает оболочка
    (ADR 0002). В Python это обычный файл — ни `pywin32`, ни асинхронного
    цикла не требуется.
    """

    def __init__(self, name: str):
        self.name = name
        self._file = None
        self._lock = threading.Lock()

    @staticmethod
    def path(session: str, channel: str) -> str:
        return rf"\\.\pipe\rina.{session}.{channel}"

    def connect(self, timeout: float = 10.0) -> "PipeClientTransport":
        """
        Подключиться, подождав, пока оболочка поднимет канал.

        Ожидание нужно потому, что порядок запуска не гарантирован: оболочка
        запускает ядро и создаёт каналы, и кто из двух окажется быстрее —
        вопрос планировщика, а не замысла.
        """
        import time as _time
        deadline = _time.monotonic() + timeout
        last = None
        while _time.monotonic() < deadline:
            try:
                self._file = open(self.name, "r+b", buffering=0)
                return self
            except OSError as exc:
                last = exc
                _time.sleep(0.05)
        raise TransportClosed(
            f"канал {self.name} не открылся за {timeout} с: {last}")

    def send(self, data: bytes) -> None:
        if self._file is None:
            raise TransportClosed("канал не открыт")
        with self._lock:
            try:
                self._file.write(data)
                self._file.flush()
            except OSError as exc:
                raise TransportClosed(str(exc)) from None

    def recv(self, max_bytes: int = 65536) -> bytes:
        if self._file is None:
            raise TransportClosed("канал не открыт")
        try:
            chunk = self._file.read(max_bytes)
        except OSError as exc:
            raise TransportClosed(str(exc)) from None
        if not chunk:
            raise TransportClosed("оболочка закрыла канал")
        return chunk

    def close(self) -> None:
        if self._file is not None:
            try:
                self._file.close()
            finally:
                self._file = None


def open_channels(mode: str, session: str = "") -> Channels:
    """Собрать каналы по имени режима. Используется точкой входа `4.0-E01`."""
    if mode == "stdio":
        return Channels(StdioTransport())
    if mode == "pipe":
        if not session:
            raise ValueError("режиму pipe нужен идентификатор сессии")
        control = PipeClientTransport(
            PipeClientTransport.path(session, "control")).connect()
        data = PipeClientTransport(
            PipeClientTransport.path(session, "data")).connect()
        return Channels(control, data)
    raise ValueError(f"неизвестный транспорт: {mode!r}")
