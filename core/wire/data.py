"""
The data channel and backpressure.

Plan items `4.0-D07` (the binary channel) and `4.0-D08` (the credit scheme);
specification, §2 and §8.

**Binary data is never encoded inside JSON.** Base64 inflates the volume by
a third, but the matter is not volume: encoded sound travels over the
control channel and joins the same queue as commands. While a second of
speech travels, a button press waits — and that is not a slow channel but a
wrongly built one.

Hence two channels per session and two different frames. The control one
carries JSON, the data channel carries bytes with a short binary header:

    [4 bytes: length of the rest of the frame][4: stream_id][8: sequence number][bytes]

The sequence number grows within a stream and is there for detecting losses
while debugging: without it a lost chunk of sound looks like "Rina did not
catch all of it", and the cause has to be hunted in recognition rather than
in the channel.

**The credit scheme.** The receiver announces how many bytes it is ready to
take; the sender has no right to keep more than that in flight. The initial
credit is zero, that is, the sender stays silent until it is called on.
Without this a fast source of frames or sound overflows the queue and drags
memory away — a failure that looks from outside like "the program ate a
gigabyte" and from inside like nothing at all.

The initial credit is precisely zero rather than "a little in advance": a
receiver that is not ready yet must not get data at all. An advance would
turn the mistake "we forgot to issue credit" into a rarely reproducible one
— it would show up only on streams longer than the advance.
"""

import struct
from dataclasses import dataclass, field
from typing import Iterator

from core.wire.errors import (ERROR_FRAME_TOO_LARGE, ERROR_INVALID_PAYLOAD,
                              ERROR_INVALID_STATE, fault)

#: The limit of one data frame (§2). Smaller than the control one: a frame of
#: sound need not be large, and fine slicing gives responsiveness and even
#: pressure.
DATA_FRAME_LIMIT = 256 * 1024

#: The data frame's header after the length field: the stream number and the sequence number.
_HEADER = struct.Struct(">I")
_INNER = struct.Struct(">IQ")

#: The kinds of stream (§8) and the capability without which a kind is not opened.
KINDS = {
    "audio.input": "audio.input",     # the microphone, shell to core
    "audio.output": "audio.output",   # synthesis, core to shell
    "screen.frame": "actuation",      # 5.0, shell to core
}


def capability_for_kind(kind: str) -> str:
    """Which capability the correspondent must declare to accept such a kind."""
    try:
        return KINDS[kind]
    except KeyError:
        raise fault(ERROR_INVALID_PAYLOAD, f"неизвестный вид потока: {kind!r}",
                    kind=kind) from None


@dataclass(frozen=True)
class DataFrame:
    stream_id: int
    seq: int
    payload: bytes


def encode_data_frame(frame: DataFrame) -> bytes:
    body = _INNER.pack(frame.stream_id, frame.seq) + frame.payload
    if len(body) > DATA_FRAME_LIMIT:
        raise fault(ERROR_FRAME_TOO_LARGE,
                    "кадр данных больше предела канала",
                    size=len(body), limit=DATA_FRAME_LIMIT)
    return _HEADER.pack(len(body)) + body


class DataFrameDecoder:
    """
    Assembling data frames out of a stream of bytes.

    The limit, as in the control channel, is checked **against the declared
    length, before memory is allocated**: otherwise it protects against
    nothing.
    """

    def __init__(self, limit: int = DATA_FRAME_LIMIT):
        self._limit = limit
        self._buffer = bytearray()

    def feed(self, chunk: bytes) -> Iterator[DataFrame]:
        self._buffer.extend(chunk)
        while True:
            if len(self._buffer) < _HEADER.size:
                return
            (size,) = _HEADER.unpack_from(self._buffer, 0)
            if size > self._limit:
                raise fault(ERROR_FRAME_TOO_LARGE,
                            "объявленный размер кадра данных больше предела",
                            size=size, limit=self._limit)
            if size < _INNER.size:
                raise fault(ERROR_INVALID_PAYLOAD,
                            "кадр данных короче собственного заголовка",
                            size=size)
            if len(self._buffer) < _HEADER.size + size:
                return
            start = _HEADER.size
            stream_id, seq = _INNER.unpack_from(self._buffer, start)
            payload = bytes(self._buffer[start + _INNER.size:start + size])
            del self._buffer[:_HEADER.size + size]
            yield DataFrame(stream_id, seq, payload)

    @property
    def pending(self) -> int:
        return len(self._buffer)


@dataclass
class Credit:
    """
    Permission to send, issued by the receiver (§8).

    Counted in bytes rather than in frames: bytes are what eat memory, and a
    stream of a thousand small frames is no better than ten large ones of
    the same volume.
    """

    granted: int = 0
    sent: int = 0

    @property
    def available(self) -> int:
        return self.granted - self.sent

    def grant(self, extra: int) -> int:
        if extra <= 0:
            raise fault(ERROR_INVALID_PAYLOAD,
                        "кредит выдаётся положительным числом байт",
                        bytes=extra)
        self.granted += extra
        return self.available

    def spend(self, size: int) -> None:
        if size > self.available:
            raise fault(ERROR_INVALID_STATE,
                        "отправитель превысил выданный кредит",
                        size=size, available=self.available)
        self.sent += size


class DataSender:
    """
    The sending side of the data channel.

    Credit is kept **per stream**: the microphone and synthesis run at the
    same time and in different directions, and a common tally would tie
    their speeds to each other for no reason whatever.
    """

    def __init__(self):
        self._seq: dict[int, int] = {}
        self._credit: dict[int, Credit] = {}
        self.open: dict[int, str] = {}

    def open_stream(self, stream_id: int, kind: str) -> None:
        capability_for_kind(kind)          # an unknown kind: refused at once
        if stream_id in self.open:
            raise fault(ERROR_INVALID_STATE, f"поток {stream_id} уже открыт",
                        stream_id=stream_id)
        self.open[stream_id] = kind
        self._seq[stream_id] = 0
        self._credit[stream_id] = Credit()

    def grant(self, stream_id: int, extra: int) -> int:
        """The receiver sent `stream.credit`."""
        return self._require(stream_id).grant(extra)

    def available(self, stream_id: int) -> int:
        return self._require(stream_id).available

    def send(self, stream_id: int, payload: bytes) -> bytes:
        """
        Assemble a frame, debiting the credit. The frame is returned — the
        caller sends it.

        Sending without credit is not "a little ahead" but an error: a
        receiver that announced zero is not ready to receive at all.
        """
        credit = self._require(stream_id)
        credit.spend(len(payload))
        self._seq[stream_id] += 1
        return encode_data_frame(
            DataFrame(stream_id, self._seq[stream_id], payload))

    def close_stream(self, stream_id: int) -> None:
        self._require(stream_id)
        del self.open[stream_id]
        del self._seq[stream_id]
        del self._credit[stream_id]

    def close_all(self) -> int:
        """Close every stream: breaking the data channel closes them all (§8)."""
        count = len(self.open)
        self.open.clear()
        self._seq.clear()
        self._credit.clear()
        return count

    def _require(self, stream_id: int) -> Credit:
        if stream_id not in self.open:
            raise fault(ERROR_INVALID_STATE,
                        f"поток {stream_id} не открыт или уже закрыт",
                        stream_id=stream_id)
        return self._credit[stream_id]


class DataReceiver:
    """
    The receiving side: assembles the stream and watches for gaps.

    A gap in the sequence number does not break off reception. The channel
    does not lose frames by itself — if a gap happened, one of the sides is
    to blame, and it is more useful to record the fact with the numbers than
    to fall over: a receiver that has fallen over will not tell where
    exactly it tore.
    """

    def __init__(self, window: int = 64 * 1024):
        self.window = window
        self._expected: dict[int, int] = {}
        self.data: dict[int, bytearray] = {}
        self.gaps: list[tuple[int, int, int]] = []
        self.consumed: dict[int, int] = {}

    def accept(self, frame: DataFrame) -> None:
        expected = self._expected.get(frame.stream_id, 0) + 1
        if frame.seq != expected:
            self.gaps.append((frame.stream_id, expected, frame.seq))
        self._expected[frame.stream_id] = frame.seq
        self.data.setdefault(frame.stream_id, bytearray()).extend(frame.payload)
        self.consumed[frame.stream_id] = (
            self.consumed.get(frame.stream_id, 0) + len(frame.payload))

    def take_credit(self, stream_id: int) -> int:
        """
        How many bytes to announce to the sender after handling what was
        received.

        The receiver issues credit as it handles data, not as it receives
        it: credit for what lies unhandled in the buffer is precisely the
        unbounded queue the scheme exists to do away with.
        """
        ready = self.consumed.pop(stream_id, 0)
        return min(ready, self.window) if ready else 0
