"""
The transport: how bytes get to the other side.

Plan item `4.0-E01`; the transport decision is
[ADR 0002](../../docs/adr/0002-ipc-transport.md).

The protocol does not depend on the transport — that is written down in
ADR 0002 and is checked by the conformance suite, which drives the same
contract over an in-process transport. Gathered here are the
implementations, and every one of them can do exactly three things: give out
bytes, take bytes, close.

**The named pipe is held by the shell, the core connects as a client.** An
inversion of the usual layout, and it is also what removes a dependency: in
Python a client is an ordinary `open(r'\\\\.\\pipe\\...', 'r+b')`, whereas a
server would demand `pywin32` or a Proactor loop.

**The `stdio` mode is the answer to that decision's only price.** ADR 0002
honestly recorded that a pipe has neither `netstat` nor packet capture, and
turned down a TCP debugging mode: a port without authentication that will
one day be left switched on. Standard input and output do not have that
drawback — it is not a listening point, it cannot be connected to from
outside, it lives exactly as long as the started process. Debugging is
possible, and no hole appears.
"""

import os
import queue
import sys
import threading
import time

try:                                  # Windows only; on another system we
    import msvcrt                     # have no named pipes anyway
except ImportError:                   # pragma: no cover
    msvcrt = None                     # type: ignore[assignment]


def _peek_named_pipe():
    """`PeekNamedPipe`, or `None` if there is nothing to peek into the pipe with."""
    if msvcrt is None or not sys.platform.startswith("win"):
        return None
    import ctypes
    from ctypes import wintypes

    peek = ctypes.WinDLL("kernel32", use_last_error=True).PeekNamedPipe
    peek.argtypes = [wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD,
                     ctypes.POINTER(wintypes.DWORD),
                     ctypes.POINTER(wintypes.DWORD),
                     ctypes.POINTER(wintypes.DWORD)]
    peek.restype = wintypes.BOOL
    return peek


class TransportClosed(Exception):
    """The other side closed. For the core this means "the shell is gone"."""


class Transport:
    """One stream of bytes in both directions."""

    def send(self, data: bytes) -> None:
        raise NotImplementedError

    def recv(self, max_bytes: int = 65536) -> bytes:
        """
        Read whatever there is.

        Empty bytes mean "there is nothing right now", not "it is all over".
        The end of the stream is `TransportClosed`, and the transport itself
        says so: for a pipe an empty read means closure, for an in-process
        queue it means the message has not been put there yet. A server that
        guesses this from the object's kind will be wrong on the very first
        new transport — and wrong in silence, spinning an empty loop instead
        of finishing.
        """
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError


class Channels:
    """
    A session's pair of channels: control and data.

    There may be no data channel — for instance in `stdio` mode, where there
    is one stream. This is not a breakage: the data channel is needed by
    sound, and what is usually debugged is commands. The absence is
    expressed explicitly, so that an attempt to open a stream runs into an
    intelligible refusal rather than into a `None` in the middle of sending.
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
    An in-process transport: for tests and for conformance.

    It exists not for the tests' convenience but because ADR 0002 demands
    it: a protocol that cannot be driven past the pipe depends on the pipe —
    it simply does not know that yet.
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
    The control channel over standard input and output.

    Binary streams, not text ones: a frame carries four bytes of length, and
    a text wrapper with newline translation would spoil them in silence.
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
            # On standard input an empty read happens only once — the end.
            raise TransportClosed("стандартный ввод закрыт")
        return chunk

    def close(self) -> None:
        try:
            self._out.flush()
        except Exception:
            pass


class PipeClientTransport(Transport):
    """
    A Windows named-pipe client.

    The core connects rather than listens: the pipe's server is the shell
    (ADR 0002). In Python this is an ordinary file — neither `pywin32` nor
    an asynchronous loop is needed.

    **Reading has no right to lock writing out, and that cost a separate
    decision.** On a synchronous Windows file descriptor, operations are
    serialised: while the main thread hangs in `ReadFile`, a `WriteFile`
    from a worker thread waits for it to finish. The core meanwhile stays
    silent until the shell sends something — that is, push events (§10) do
    not work at all, and it looks like "the core has gone off to think".

    The defect turned up only on a real pipe: the in-process conformance
    suite could not catch it by construction — there is neither a descriptor
    nor serialisation there, and the protocol has nothing to do with it.
    Hence the rule: the protocol's independence from the transport
    (ADR 0002) does not do away with checking the transport itself, and
    `shell/Rina.Protocol.Probe` is that check.

    It is cured without third-party libraries: one lock per descriptor and
    `PeekNamedPipe` before reading. `ReadFile` is called only once the bytes
    have already arrived, so there is nothing to hang on inside the lock,
    and a write always finds the descriptor free. The price is polling every
    few milliseconds; the alternative (overlapped I/O) demands `pywin32`,
    and its absence was half of ADR 0002's argument for this layout.
    """

    #: How often to peek into the pipe when it is empty.
    POLL = 0.004

    def __init__(self, name: str):
        self.name = name
        self._file = None
        self._lock = threading.RLock()
        self._peek = _peek_named_pipe()

    @staticmethod
    def path(session: str, channel: str) -> str:
        return rf"\\.\pipe\rina.{session}.{channel}"

    def connect(self, timeout: float = 10.0) -> "PipeClientTransport":
        """
        Connect, having waited for the shell to raise the pipe.

        The wait is needed because the start order is not guaranteed: the
        shell starts the core and creates the pipes, and which of the two
        turns out faster is a question for the scheduler rather than for the
        design.
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
        """
        Read what is available. Empty bytes mean "nothing yet", not "the
        end".

        The lock is held only for the duration of the read itself, and we
        read only when `PeekNamedPipe` has already counted bytes. Without
        this a sending thread would wait for somebody else's read to finish.
        """
        if self._file is None:
            raise TransportClosed("канал не открыт")
        with self._lock:
            if self._file is None:
                raise TransportClosed("канал закрыт")
            available = self._available()
            if available == 0:
                return b""
            try:
                chunk = self._file.read(min(available, max_bytes))
            except OSError as exc:
                raise TransportClosed(str(exc)) from None
        if not chunk:
            raise TransportClosed("оболочка закрыла канал")
        return chunk

    def _available(self) -> int:
        """
        How many bytes are already lying in the pipe. Zero means empty, an
        exception means the end.

        If there is nothing to peek with (not Windows, the descriptor
        unavailable), we assume there are bytes: behaviour then falls back
        to a plain blocking read, and nothing gets worse than it was.
        """
        if self._peek is None:
            time.sleep(self.POLL)
            return 65536
        import ctypes

        count = ctypes.c_ulong(0)
        try:
            handle = msvcrt.get_osfhandle(self._file.fileno())
        except (OSError, ValueError):
            raise TransportClosed("дескриптор канала потерян") from None
        ok = self._peek(ctypes.c_void_p(handle), None, 0, None,
                        ctypes.byref(count), None)
        if not ok:
            raise TransportClosed("оболочка закрыла канал")
        if count.value == 0:
            time.sleep(self.POLL)
        return int(count.value)

    def close(self) -> None:
        with self._lock:
            if self._file is not None:
                try:
                    self._file.close()
                finally:
                    self._file = None


def open_channels(mode: str, session: str = "") -> Channels:
    """Assemble the channels by mode name. Used by the `4.0-E01` entry point."""
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
