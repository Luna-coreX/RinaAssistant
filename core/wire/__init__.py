"""
Провод: реализация протокола «оболочка ↔ ядро» версии 1.

Спецификация — [`docs/protocol/PROTOCOL-v1.md`](../../docs/protocol/PROTOCOL-v1.md).
Она написана до реализации, и этот пакет ей подчиняется, а не наоборот:
расхождение между кодом и документом означает, что неправ код, либо что
документ надо править осознанно и отдельным решением.

**Почему пакет называется не `protocol`.** Модуль `core/protocol.py` уже
занят — там перечень событий 3.1.0, по которому сверялась спецификация. Это
разные вещи: там каталог того, что ядро сообщает, здесь — как сообщение
устроено, разложено на байты и как две стороны договариваются о версии.
Каталог событий переедет сюда вместе с E02; до тех пор соседство временное,
и одинаковое имя запутывало бы обоих.

Пакет не знает ни о Qt, ни о канале. Он умеет превращать сообщение в байты и
обратно и следить за состоянием сессии; кто эти байты переносит — именованный
канал, сокет или очередь внутри процесса — его не касается. Так требует
ADR 0002: спецификация не зависит от транспорта, чтобы conformance-тесты
(`4.0-D16`) могли гонять её через транспорт внутри процесса.

Состав:

    errors      форма ошибки как части контракта (§5)
    envelope    конверт и кадрирование управляющего канала (4.0-D04, §2–3)
    handshake   рукопожатие, версии и возможности (4.0-D03, §4)
"""

from core.wire.envelope import (CONTROL_FRAME_LIMIT, Envelope, FrameDecoder,
                                IdGenerator, MessageType, decode, encode,
                                encode_frame, new_trace_id)
from core.wire.errors import (ProtocolError, ProtocolFault, CATEGORIES,
                              ERROR_FRAME_TOO_LARGE, ERROR_INCOMPATIBLE,
                              ERROR_INVALID_ENVELOPE, ERROR_NOT_READY,
                              ERROR_UNKNOWN_METHOD)
from core.wire.handshake import (CAPABILITIES, CORE_CAPABILITIES,
                                 SHELL_CAPABILITIES, Session, SessionState,
                                 Side, capability_of, negotiate)

__all__ = [
    "CONTROL_FRAME_LIMIT", "Envelope", "FrameDecoder", "IdGenerator",
    "MessageType", "decode", "encode", "encode_frame", "new_trace_id",
    "ProtocolError", "ProtocolFault", "CATEGORIES",
    "ERROR_FRAME_TOO_LARGE", "ERROR_INCOMPATIBLE", "ERROR_INVALID_ENVELOPE",
    "ERROR_NOT_READY", "ERROR_UNKNOWN_METHOD",
    "CAPABILITIES", "CORE_CAPABILITIES", "SHELL_CAPABILITIES", "Session",
    "SessionState", "Side", "capability_of", "negotiate",
]
