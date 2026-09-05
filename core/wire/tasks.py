"""
Long tasks and cooperative cancellation.

Plan items `4.0-D09` (the life cycle) and `4.0-D10` (cancellation);
specification, §9.

A coding task in RinaNeuro runs for minutes. The request-response model does
not express that: it has only "has not answered yet" and "answered", and
everything interesting lies between them — how much is done, what has come
out so far, whether it can be stopped. So the life cycle is laid down now,
while the price is nil, although 4.0 has no long tasks.

    accepted ──> running ──┬──> done
                           ├──> failed
                           └──> cancelled
                  (progress, partial — any number of times)

**Exactly one of `done`/`failed`/`cancelled` ends a task.** This is the main
invariant, and it is checked rather than assumed: a side that received two
final events does not know which to believe, and one that received none
waits forever. After a final event, any other message about the task is a
defect of the sender (`protocol.invalid_state`).

**Cancellation is three steps, not one.**

    task.cancel ──> answer {accepted} ──> … the actual stop … ──> task.cancelled

Acknowledging receipt of the request is not the same as stopping, and the
two must not be confused: a cancellation that silently does nothing is worse
than no cancellation. Cancellation is cooperative: the task notices the
request itself and stops where that is safe — interrupting somebody else's
work at an arbitrary point means leaving a half-written file behind.

**The race is described and resolved.** If the task finished by itself
before the cancellation arrived, `done` comes and `task.cancelled` does not
come at all. The specification requires the requesting side to withstand
this; here the same race is honestly reflected in the answer to
`task.cancel` — `accepted: false` together with the current state. An answer
of `true` that would never be followed by `task.cancelled` would be a
promise nobody intended to keep.
"""

from dataclasses import dataclass, field
from typing import Any, Callable

from core.wire.envelope import Envelope
from core.wire.errors import ERROR_INVALID_STATE, fault
from core.wire.events import event


class TaskState:
    ACCEPTED = "accepted"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


#: States there is no way out of.
FINAL = (TaskState.DONE, TaskState.FAILED, TaskState.CANCELLED)

#: What `task.cancel` answers about a task nothing is known about.
STATUS_UNKNOWN = "unknown"


@dataclass
class Task:
    """
    One long task on the side that performs it.

    The task knows nothing of the channel and nothing of who is listening to
    it: it returns ready-made messages, and the caller sends them. That way
    it can be run in a test without a transport — and that is how the
    `4.0-D16` conformance tests will run it too.
    """

    id: str
    ids: Any                      # IdGenerator: message numbers
    state: str = TaskState.ACCEPTED
    cancel_requested: bool = False
    events: list[Envelope] = field(default_factory=list)

    # -- the answer to the request that spawned the task ----------------------

    def accepted_payload(self) -> dict[str, Any]:
        """The body of the answer to the request: the task is accepted, work has begun."""
        return {"task_id": self.id, "status": TaskState.ACCEPTED}

    # -- the course of the work -----------------------------------------------

    def start(self) -> None:
        self._require_live("начать")
        self.state = TaskState.RUNNING

    def progress(self, note: str, fraction: float | None = None) -> Envelope:
        """
        Report progress.

        A note is required, a fraction is not: not every task knows the
        fraction, and progress without words reports nothing except that the
        process is alive.
        """
        self._require_live("сообщить о прогрессе")
        payload: dict[str, Any] = {"task_id": self.id, "note": note}
        if fraction is not None:
            payload["fraction"] = fraction
        return self._emit("task.progress", payload)

    def partial(self, result: Any) -> Envelope:
        self._require_live("отдать промежуточный результат")
        return self._emit("task.partial",
                          {"task_id": self.id, "result": result})

    # -- finishing --------------------------------------------------------------

    def done(self, result: Any) -> Envelope:
        self._finish(TaskState.DONE, "завершить")
        return self._emit("task.done", {"task_id": self.id, "result": result})

    def failed(self, error) -> Envelope:
        """`error` is either a `ProtocolError` or a ready-made dict per §5."""
        self._finish(TaskState.FAILED, "завалить")
        payload = error.to_payload() if hasattr(error, "to_payload") else error
        return self._emit("task.failed",
                          {"task_id": self.id, "error": payload})

    def cancelled(self) -> Envelope:
        """
        The task really has stopped.

        Sent only after the work has ceased — that is the whole point of the
        third step. Sending it instead of an acknowledgement means lying
        about nothing running any more.
        """
        self._finish(TaskState.CANCELLED, "отменить")
        return self._emit("task.cancelled", {"task_id": self.id})

    # -- cancellation -----------------------------------------------------------

    def request_cancel(self) -> dict[str, Any]:
        """
        Accept a request to cancel. Returns the body of the answer to
        `task.cancel`.

        Does not stop the task: it is obliged to stop itself, on noticing
        the flag.
        """
        if self.state in FINAL:
            return {"accepted": False, "status": self.state}
        self.cancel_requested = True
        return {"accepted": True, "status": self.state}

    @property
    def finished(self) -> bool:
        return self.state in FINAL

    # -- internals --------------------------------------------------------------

    def _emit(self, name: str, payload: dict[str, Any]) -> Envelope:
        message = event(name, payload, id=self.ids.next())
        self.events.append(message)
        return message

    def _require_live(self, what: str) -> None:
        if self.state in FINAL:
            raise fault(ERROR_INVALID_STATE,
                        f"нельзя {what}: задача уже {self.state}",
                        task_id=self.id, state=self.state)

    def _finish(self, new_state: str, what: str) -> None:
        self._require_live(what)
        self.state = new_state


class Registry:
    """
    A side's live tasks.

    Finished tasks are not deleted at once: a `task.cancel` for a task that
    has just finished is an ordinary race rather than a defect, and
    answering it with "there is no such task" would send debugging down a
    false trail. The last known outcome is kept, which is enough to tell
    "too late" from "wrong identifier".
    """

    def __init__(self, ids, prefix: str = "task-"):
        self._ids = ids
        self._prefix = prefix
        self._n = 0
        self.tasks: dict[str, Task] = {}

    def create(self) -> Task:
        self._n += 1
        task = Task(id=f"{self._prefix}{self._n:04d}", ids=self._ids)
        self.tasks[task.id] = task
        return task

    def clear(self) -> int:
        """
        Forget every task — on a disconnection (`4.0-D14`).

        Forget precisely, not cancel: to cancel means to report
        `task.cancelled`, and there is nobody to report to — the
        correspondent is gone.
        """
        count = len(self.tasks)
        self.tasks.clear()
        return count

    def get(self, task_id: str) -> Task | None:
        return self.tasks.get(task_id)

    def cancel(self, task_id: str) -> dict[str, Any]:
        """
        Handle `task.cancel`. The answer body follows §9.

        An unknown identifier is not an error: most often it is a task the
        side has already forgotten. The answer tells the truth — there is
        nothing to accept.
        """
        task = self.tasks.get(task_id)
        if task is None:
            return {"accepted": False, "status": STATUS_UNKNOWN}
        return task.request_cancel()


def run(task: Task, steps: int, clock: Callable[[], float],
        advance: Callable[[float], None], *, seconds: float,
        partial_every: int = 0) -> list[Envelope]:
    """
    Run a task step by step — the §15.7 stub without waiting in real time.

    The clock is passed in from outside: the specification's requirement
    speaks of a sixty-second task, and checking it by really waiting would
    mean holding the check for a minute for the sake of a shape that does
    not depend on the duration. A fake clock gives the same sequence of
    events in milliseconds.

    Cancellation is checked **before** each step: a task that notices the
    request only after the last step is formally cooperative and practically
    useless.
    """
    task.start()
    started = clock()
    per_step = seconds / steps
    for step in range(1, steps + 1):
        if task.cancel_requested:
            task.cancelled()
            return task.events
        advance(per_step)
        task.progress(f"шаг {step} из {steps}", fraction=step / steps)
        if partial_every and step % partial_every == 0:
            task.partial({"step": step, "elapsed": round(clock() - started, 3)})
    task.done({"elapsed": round(clock() - started, 3)})
    return task.events
