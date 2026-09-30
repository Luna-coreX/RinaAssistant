"""
The wire: the implementation of the shell-to-core protocol, version 1.

The specification is
[`docs/protocol/PROTOCOL-v1.md`](../../docs/protocol/PROTOCOL-v1.md). It was
written before the implementation, and this package obeys it rather than the
other way round: a divergence between the code and the document means either
that the code is wrong, or that the document has to be changed deliberately
and as a separate decision.

**Why the package is not called `protocol`.** The module `core/protocol.py`
is already taken — it holds the 3.1.0 catalogue of events the specification
was checked against. These are different things: there, a catalogue of what
the core reports; here, how a message is built, laid out in bytes, and how
the two sides agree on a version. The event catalogue will move here with
E02; until then the neighbourhood is temporary, and one name would confuse
both.

The package knows nothing of Qt and nothing of the channel. It can turn a
message into bytes and back and keep track of the session's state; who
carries those bytes — a named pipe, a socket or an in-process queue — is
none of its business. ADR 0002 requires this: the specification does not
depend on the transport, so that the conformance tests (`4.0-D16`) can drive
it over an in-process transport.

Contents:

    errors      the error catalogue as part of the contract (4.0-D05, §5)
    envelope    the envelope and control-channel framing (4.0-D04, §2-3)
    handshake   the handshake, versions and capabilities (4.0-D03, §4)
    events      the event catalogue and streamed text (4.0-D11, 4.0-D06, §7, §10)
    tasks       the life cycle of a long task and cancellation (4.0-D09, D10, §9)
    data        the data channel and backpressure (4.0-D07, D08, §2, §8)
    permissions the permission channel over the C05 loop (4.0-D12, §11)
    liveness    liveness, disconnection, reconnection (4.0-D14, §13)
"""

from core.wire.envelope import (CONTROL_FRAME_LIMIT, Envelope, FrameDecoder,
                                IdGenerator, MessageType, decode, encode,
                                encode_frame)
from core.wire.data import (Credit, DATA_FRAME_LIMIT, DataFrame,
                            DataFrameDecoder, DataReceiver, DataSender, KINDS,
                            capability_for_kind, encode_data_frame)
from core.wire.liveness import (MISSED_LIMIT, SILENCE, Liveness,
                                VolatileState)
from core.wire.permissions import Ask, PermissionChannel
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
from core.trace import (NO_TRACE, TraceFilter, current_trace,
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
    "Ask", "PermissionChannel",
    "MISSED_LIMIT", "SILENCE", "Liveness", "VolatileState",
    "ALL_EVENTS", "EVENTS", "Router", "STREAM_CANCELLED", "STREAM_DONE",
    "STREAM_FAILED", "StreamReceiver", "StreamSender", "event",
    "validate_event",
    "CAPABILITIES", "CORE_CAPABILITIES", "SHELL_CAPABILITIES", "Session",
    "SessionState", "Side", "capability_of", "negotiate",
    "NO_TRACE", "TraceFilter", "current_trace", "new_trace_id",
    "require_trace", "trace_scope",
]
