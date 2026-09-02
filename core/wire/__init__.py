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

    errors      каталог ошибок как части контракта (4.0-D05, §5)
    trace       сквозная трассировка через контекст (4.0-D15, §14)
    envelope    конверт и кадрирование управляющего канала (4.0-D04, §2–3)
    handshake   рукопожатие, версии и возможности (4.0-D03, §4)
    events      каталог событий и потоковый текст (4.0-D11, 4.0-D06, §7, §10)
    tasks       жизненный цикл долгой задачи и отмена (4.0-D09, D10, §9)
    data        канал данных и обратное давление (4.0-D07, D08, §2, §8)
"""

from core.wire.envelope import (CONTROL_FRAME_LIMIT, Envelope, FrameDecoder,
                                IdGenerator, MessageType, decode, encode,
                                encode_frame)
from core.wire.data import (Credit, DATA_FRAME_LIMIT, DataFrame,
                            DataFrameDecoder, DataReceiver, DataSender, KINDS,
                            capability_for_kind, encode_data_frame)
from core.wire.errors import (CATALOGUE, CATEGORIES, ErrorSpec, ProtocolError,
                              ProtocolFault, ERROR_FRAME_TOO_LARGE,
                              ERROR_INCOMPATIBLE, ERROR_INVALID_ENVELOPE,
                              ERROR_INVALID_PAYLOAD, ERROR_INVALID_STATE,
                              ERROR_NOT_READY, ERROR_UNKNOWN_METHOD,
                              fault, make)
from core.wire.events import (ALL_EVENTS, EVENTS, Router, STREAM_CANCELLED,
                              STREAM_DONE, STREAM_FAILED, StreamReceiver,
                              StreamSender, event, validate_event)
from core.wire.tasks import FINAL, Registry, Task, TaskState, run
from core.wire.handshake import (CAPABILITIES, CORE_CAPABILITIES,
                                 SHELL_CAPABILITIES, Session, SessionState,
                                 Side, capability_of, negotiate)
from core.wire.trace import (NO_TRACE, TraceFilter, current_trace,
                             new_trace_id, require_trace, trace_scope)

__all__ = [
    "CONTROL_FRAME_LIMIT", "Envelope", "FrameDecoder", "IdGenerator",
    "MessageType", "decode", "encode", "encode_frame",
    "CATALOGUE", "CATEGORIES", "ErrorSpec", "ProtocolError", "ProtocolFault",
    "ERROR_FRAME_TOO_LARGE", "ERROR_INCOMPATIBLE", "ERROR_INVALID_ENVELOPE",
    "ERROR_INVALID_PAYLOAD", "ERROR_INVALID_STATE", "ERROR_NOT_READY",
    "ERROR_UNKNOWN_METHOD", "fault", "make",
    "FINAL", "Registry", "Task", "TaskState", "run",
    "Credit", "DATA_FRAME_LIMIT", "DataFrame", "DataFrameDecoder",
    "DataReceiver", "DataSender", "KINDS", "capability_for_kind",
    "encode_data_frame",
    "ALL_EVENTS", "EVENTS", "Router", "STREAM_CANCELLED", "STREAM_DONE",
    "STREAM_FAILED", "StreamReceiver", "StreamSender", "event",
    "validate_event",
    "CAPABILITIES", "CORE_CAPABILITIES", "SHELL_CAPABILITIES", "Session",
    "SessionState", "Side", "capability_of", "negotiate",
    "NO_TRACE", "TraceFilter", "current_trace", "new_trace_id",
    "require_trace", "trace_scope",
]
