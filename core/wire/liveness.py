"""
Liveness, disconnection, reconnection.

Plan item `4.0-D14`; specification, §13.

Within one process half the program does not die: everything falls at once,
and that is visible. Across two, one side may die in silence, and the other
will wait for an answer that will never come. A window waiting on a dead
core looks frozen, and a person will not tell it apart from a slow one.

**Silence is not a sign of death.** The sign of death is silence in answer
to a direct question. So a `ping` is sent only after a pause, and a side is
considered dead after three unanswered ones in a row: one loss can happen
for any reason, three in a row is already a pattern.

**Any message counts as a pong.** There is no point pinging a busy channel:
if the correspondent has just sent an event, it is alive, and an extra
question is an expense for nothing. Hence a silence counter rather than a
timer on a schedule.

**What survives a reconnection and what does not.** Settings, commands,
history, reminders and plugins lie in the store and survive. What does not
survive: an unclosed clarifying question, open streams, granted permissions,
unfinished tasks. This is not a simplification of the implementation but a
decision: after a break it is unknown what managed to happen on the other
side, and a permission granted before the break belongs to a conversation
that no longer exists.

So the state after the handshake is **assembled afresh by requests, not
restored from memory**. The memory of the surviving side is not a source of
truth about what is going on at the correspondent.
"""

import time
from dataclasses import dataclass, field
from typing import Any, Callable

#: After how much silence to ask "are you alive" (§13).
SILENCE = 5.0

#: How many unanswered questions in a row count as death.
MISSED_LIMIT = 3


class Liveness:
    """
    The counter of silence and unanswered questions on one side.

    It sends nothing itself: it decides whether it is time, and counts. The
    sending is done by whoever has the channel — that way this logic can be
    checked on a fake clock without raising a transport.
    """

    def __init__(self, silence: float = SILENCE,
                 missed_limit: int = MISSED_LIMIT,
                 clock: Callable[[], float] = time.time):
        self._silence = silence
        self._limit = missed_limit
        self._clock = clock
        self.last_seen = clock()
        self.missed = 0
        self._awaiting = False

    def note_traffic(self, now: float | None = None) -> None:
        """
        Any message arrived.

        It counts as an answer: a correspondent that sent an event is alive
        no less convincingly than one that sent a pong.
        """
        self.last_seen = self._clock() if now is None else now
        self.missed = 0
        self._awaiting = False

    def note_pong(self, now: float | None = None) -> None:
        self.note_traffic(now)

    def silent_for(self, now: float | None = None) -> float:
        return (self._clock() if now is None else now) - self.last_seen

    def due(self, now: float | None = None) -> bool:
        """Whether it is time to send a `ping`."""
        return self.silent_for(now) >= self._silence

    def sent_ping(self, now: float | None = None) -> None:
        """
        The question has been asked and is not yet answered.

        A second `ping` without an answer to the first is not a doubling of
        the question but a second unanswered one: those are exactly what is
        counted.
        """
        self.missed += 1
        self._awaiting = True

    @property
    def awaiting(self) -> bool:
        return self._awaiting

    def dead(self) -> bool:
        return self.missed >= self._limit

    def reset(self, now: float | None = None) -> None:
        self.note_traffic(now)


@dataclass
class VolatileState:
    """
    What a break takes with it (§13).

    Gathered in one place deliberately. Laid out among its owners, it would
    be reset in several places, and one day somewhere it would not be reset
    — and unnoticeably at that: a permission that survived a break looks
    like an ordinary permission, and it will be discovered only by firing.
    """

    permissions: Any = None      # PermissionChannel
    tasks: Any = None            # tasks.Registry
    data_streams: Any = None     # data.DataSender
    text_streams: Any = None     # events.StreamSender
    session: Any = None          # handshake.Session
    also: list[Callable[[], int]] = field(default_factory=list)

    def snapshot(self) -> dict[str, int]:
        """How much is alive right now in total — for the journal and for the check."""
        return {
            "разрешения": (self.permissions.ledger.pending()
                           if self.permissions else 0),
            "просьбы": self.permissions.pending if self.permissions else 0,
            "задачи": (len([t for t in self.tasks.tasks.values()
                            if not t.finished]) if self.tasks else 0),
            "потоки данных": (len(self.data_streams.open)
                              if self.data_streams else 0),
            "потоки текста": (len(self.text_streams.open)
                              if self.text_streams else 0),
        }

    def reset(self) -> dict[str, int]:
        """
        Reset everything that does not survive a break. Returns how much of
        what there was.

        Tasks are not "cancelled" but forgotten: to cancel means to report
        `task.cancelled`, and there is nobody to report to and no point, the
        correspondent is gone. Whoever reconnects will ask afresh.
        """
        was = self.snapshot()
        if self.permissions is not None:
            self.permissions.drop_all()
        if self.tasks is not None:
            self.tasks.clear()
        if self.data_streams is not None:
            self.data_streams.close_all()
        if self.text_streams is not None:
            self.text_streams.close_all()
        if self.session is not None:
            self.session.close()
        for extra in self.also:
            extra()
        return was
