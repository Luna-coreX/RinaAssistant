"""
The permission channel: the core asks, the shell asks the person.

Plan item `4.0-D12`; specification, §11. Rests on the confirmation loop
`4.0-C05` (`core/confirmations.py`).

The core cannot perform a dangerous action itself and cannot show windows.
It reports an intent — what will happen, why and for how long — the shell
shows this to the person and returns the decision.

**The confirmation identifier is issued by the core, not by the shell.** In
its first edition §11 of the specification returned `confirmation_id` in the
shell's answer, that is, the shell was what produced it. That directly
contradicted `4.0-C05`, where it is written down: the decision on whether an
action is confirmed must not be taken on the shell's side, or it can be
circumvented from the interface. A shell that issues identifiers can issue
any, and the core has nothing to tell a real one from an invented one — and
the whole of one-time use and binding to arguments rests precisely on the
identifier having been issued by the core for a particular call.

So, here: the core creates a **request** with a number of its own, the shell
answers "yes" or "no", and only after "yes" does the core write out a
confirmation. The shell cannot create a confirmation — it can only permit
one to be created.

**Refusal by default.** A request that is not answered in time is considered
declined. Not "we keep waiting" and not "silence means consent": silence may
mean nobody saw the window at all.

**The `session` scope from the specification has been removed.** Two remain:
`once` — one execution, `until` — until a deadline. The third described the
same thing as `until`, because §13 already says: granted permissions do not
survive a reconnection, that is, the session is the upper bound of any
scope.

**A dangerous action is not granted `until`.** A permission valid for half
an hour to shut the computer down is precisely the case confirmations were
created for. If the shell asks for such a scope, the core lowers it to
`once` and says so in the answer: the person agreed to this action, and
there is no point losing their consent — but all the less point widening it.
"""

import secrets
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from core.confirmations import ONCE, SCOPES, UNTIL, ConfirmationLedger
from core.permissions import dangerous
from core.wire.errors import ERROR_INVALID_PAYLOAD, ERROR_INVALID_STATE, fault

#: How long we wait for the person's answer if the core named no deadline.
DEFAULT_TTL = 60


@dataclass(frozen=True)
class Ask:
    """A request sent to the shell and not yet answered."""

    id: str
    permission: str
    action: str
    reason: str
    preview: str
    ttl: int
    asked_at: float
    tool: str
    args: dict[str, Any] = field(default_factory=dict)

    def deadline(self) -> float:
        return self.asked_at + self.ttl

    def to_payload(self) -> dict[str, Any]:
        """
        What goes into the channel (§11).

        The call's arguments do not go out: the shell needs to show the
        person a `preview` — what exactly will happen, in words — not a
        serialised call. The fingerprint of the arguments stays in the core,
        in the same place where it is checked.
        """
        return {
            "request_id": self.id,
            "permission": self.permission,
            "action": self.action,
            "reason": self.reason,
            "preview": self.preview,
            "ttl": self.ttl,
        }


class PermissionChannel:
    """
    The core's side of the permission channel.

    Keeps unclosed requests and writes out confirmations from the shell's
    answers. The clock is passed in from outside so that the deadline can be
    checked rather than waited out.
    """

    def __init__(self, ledger: ConfirmationLedger | None = None,
                 clock: Callable[[], float] = time.time):
        #: The default ledger is created **on the same clock**. Different
        #: time scales for the channel and for the ledger mean a deadline
        #: computed on one and checked on the other; the conformance suite
        #: caught exactly this. A ledger passed in from outside is obliged
        #: to run on the same time.
        self.ledger = ledger or ConfirmationLedger(clock=clock)
        self._clock = clock
        self._pending: dict[str, Ask] = {}

    # -- the core asks ----------------------------------------------------------

    def ask(self, tool: str, args: dict[str, Any] | None = None, *,
            permission: str, reason: str, preview: str,
            ttl: int = DEFAULT_TTL) -> Ask:
        """
        Create a request. Returns it; the caller sends it.

        `preview` is required: §11 demands showing what exactly will happen,
        not only the action's name. "Shut down the computer" and "The
        computer will be shut down immediately" are different messages, and
        the second one a person has time to take in.
        """
        if not preview.strip():
            raise fault(ERROR_INVALID_PAYLOAD,
                        "просьба обязана показать, что именно произойдёт",
                        action=tool)
        if ttl <= 0:
            raise fault(ERROR_INVALID_PAYLOAD,
                        "срок ожидания ответа обязан быть положительным",
                        ttl=ttl)
        ask = Ask(
            id="ask-" + secrets.token_urlsafe(9),
            permission=permission,
            action=tool,
            reason=reason,
            preview=preview,
            ttl=ttl,
            asked_at=self._clock(),
            tool=tool,
            args=dict(args or {}),
        )
        self._pending[ask.id] = ask
        return ask

    # -- the shell answered -----------------------------------------------------

    def resolve(self, request_id: str, granted: bool,
                scope: str = ONCE) -> dict[str, Any]:
        """
        Accept the shell's answer and, if permitted, write out a
        confirmation.

        Returns the answer body per §11. The request is closed in any case:
        it cannot be answered twice, or a "no" could be played over again.
        """
        ask = self._pending.pop(request_id, None)
        if ask is None:
            raise fault(ERROR_INVALID_STATE,
                        "ответ на просьбу, которой нет или уже закрытую",
                        request_id=request_id)
        if scope not in SCOPES:
            raise fault(ERROR_INVALID_PAYLOAD,
                        f"неизвестная область разрешения: {scope!r}",
                        scope=scope, known=list(SCOPES))

        now = self._clock()
        if now >= ask.deadline():
            return self._refusal(ask, "expired")
        if not granted:
            return self._refusal(ask, "denied")

        downgraded = False
        if scope == UNTIL and dangerous([ask.permission]):
            scope, downgraded = ONCE, True

        confirmation = self.ledger.issue(
            ask.tool, ask.args,
            ttl=max(ask.deadline() - now, 1.0),
            scope=scope, preview=ask.preview)
        return {
            "request_id": ask.id,
            "granted": True,
            "confirmation_id": confirmation.id,
            "expires_at": confirmation.expires_at,
            "scope": scope,
            "downgraded": downgraded,
        }

    def expire(self, now: float | None = None) -> int:
        """
        Close requests that were not answered. Returns how many.

        Called on a timer: a request everybody has forgotten about must not
        stay open — otherwise a late answer permits an action the person no
        longer remembers.
        """
        now = self._clock() if now is None else now
        dead = [i for i, a in self._pending.items() if now >= a.deadline()]
        for i in dead:
            del self._pending[i]
        return len(dead)

    @property
    def pending(self) -> int:
        return len(self._pending)

    def drop_all(self) -> int:
        """
        Forget everything: unclosed requests and issued confirmations.

        Needed on a disconnection (`4.0-D14`). A permission granted before
        the break belongs to a conversation that no longer exists: it is
        unknown what managed to happen on the other side, and the person who
        agreed a minute ago was not agreeing to this.
        """
        count = len(self._pending) + self.ledger.pending()
        self._pending.clear()
        self.ledger.revoke_all()
        return count

    def _refusal(self, ask: Ask, why: str) -> dict[str, Any]:
        return {
            "request_id": ask.id,
            "granted": False,
            "confirmation_id": None,
            "expires_at": None,
            "scope": ONCE,
            "reason": why,
        }
