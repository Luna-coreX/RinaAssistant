"""
End-to-end tracing.

Plan item `4.0-D15`; specification, §14.

**It lies in the core rather than in the wire package**, although it
appeared for the protocol's sake. Tracing is entirely the core's business:
a chain begins where the action began, and the first consumer outside the
wire turned out to be the engine itself, which has to mark a reminder that
fired (`4.0-E05`). The module knows nothing of the envelope or the channel;
keeping it in the wire would mean making journalling drag the protocol
along behind it.

A `trace_id` is born where the action began — a click in the shell or a
recognised phrase — and is carried into **every** message that action gives
rise to, including events and errors.

This is the only way to debug a two-process system. Without it, two journals
hold two unconnected sets of lines, and the question "what exactly happened
after that click" is answered by comparing timestamps — that is, by
guesswork.

**Why a context rather than a parameter.** An event is born deep down: the
tool registry calls the execution, the execution raises the event. The
`trace_id` could be dragged through the whole chain as a parameter, but then
every new function on the path is obliged to accept and pass it, and one day
somebody will not — and in silence at that, because an event without a trace
looks perfectly normal. `contextvars` makes losing it impossible by
construction: the value lives in the execution context, not in signatures.

`contextvars` rather than `threading.local`: the context is inherited by
asyncio tasks, and after `4.0-E01` the core will become an asynchronous
service.
"""

import contextvars
import uuid
from contextlib import contextmanager

_current: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "rina_trace", default=None)

#: What is written to the journal when there is no action: background work,
#: startup, a timer that fired by itself. A dash is more honest than an
#: invented identifier.
NO_TRACE = "-"


def new_trace_id() -> str:
    """The beginning of a new chain."""
    return "t-" + uuid.uuid4().hex[:12]


def current_trace() -> str | None:
    """The identifier of the action being handled right now."""
    return _current.get()


def require_trace() -> str:
    """
    The current trace; if there is no action, a new one.

    The protocol forbids a message without a `trace_id` (§3), so this is not
    a refusal but a birth: better a chain of one link than an unsent
    message.
    """
    return _current.get() or new_trace_id()


@contextmanager
def trace_scope(trace_id: str | None = None):
    """
    The handling of one action.

    Entering the scope without an argument begins a new chain — that is what
    is done where an action is born: a click, a recognised phrase, a
    reminder that fired. With an argument, somebody else's chain, arrived
    from the channel, is continued.
    """
    token = _current.set(trace_id or new_trace_id())
    try:
        yield _current.get()
    finally:
        _current.reset(token)


class TraceFilter:
    """
    Substituting the trace into journal records.

    A filter rather than a formatter: a record created around our paths will
    get the field all the same, and the format will not fall over with a
    `KeyError` in the middle of looking into a failure — at exactly the
    moment the journal is needed most.
    """

    def filter(self, record):
        if not hasattr(record, "trace"):
            record.trace = _current.get() or NO_TRACE
        return True
