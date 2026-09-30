"""
The loop that confirms dangerous actions.

Plan item 4.0-C05. In 3.1.0 a confirmation lived as a `pending` dict inside
the core: with no identifier, no deadline and no one-time use. Checking that
a dangerous action was confirmed could only be done by trusting the order of
calls — that is, not at all.

Here a confirmation becomes a thing that can be presented:

    confirmation_id   issued for a particular call
    a deadline        an expired one is not accepted
    one-time use      what is presented burns up

Three properties, each of which closes off its own way of going wrong.

**Bound to the arguments, not only to the tool.** Consent to "sleep" cannot
be presented for "shut down": that is one `power_action` tool with different
arguments, and without a fingerprint of the arguments the substitution would
go through. A person confirms what they were shown, not the name of a
function.

**One-time use.** Otherwise one consent would serve until the deadline for
any number of calls — that is, "shut down the computer", confirmed once,
would shut it down a second time as well, when the phrase was recognised by
accident.

There is no Qt here: the module lies in the core.
"""

import hashlib
import json
import secrets
import threading
import time
from dataclasses import dataclass


#: How long an issued confirmation lives. The same as the deadline of an
#: unclosed question (core/dialog.py): both are a window during which a
#: person's answer still belongs to the question that was asked.
DEFAULT_TTL = 60

#: The scope.
#:
#: There are two, not three as was written down in §11 of the specification.
#: "Until the end of the session" was removed not out of caution but because
#: there is no separate mechanism for it: §13 says outright that granted
#: permissions do not survive a reconnection, that is, the session is the
#: upper bound for any scope. A third name for the same behaviour is an
#: invitation to think it is something else.
#:
#: The former name SESSION described precisely today's UNTIL: a confirmation
#: stayed valid until the deadline expired, and not at all until the end of
#: the session. A name that promises something other than what the code does
#: is a blank for a future mistake.
ONCE = "once"          # burns up at the first presentation
UNTIL = "until"        # valid until expires_at, any number of times
SCOPES = (ONCE, UNTIL)


class ConfirmationError(Exception):
    """The confirmation was not accepted. Carries a code for the protocol."""

    def __init__(self, message, code, details=None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details or {}


def fingerprint(tool_name, args):
    """
    A call's fingerprint: the tool plus the arguments.

    Computed from a canonical form, so that the order of keys does not
    change the result — otherwise a confirmation would stop matching
    itself.
    """
    payload = json.dumps({"tool": tool_name, "args": args or {}},
                         sort_keys=True, ensure_ascii=False,
                         separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


@dataclass(frozen=True)
class Confirmation:
    """Permission granted for one particular call."""

    id: str
    tool: str
    fingerprint: str
    issued_at: float
    expires_at: float
    scope: str = ONCE
    #: What the person was shown. Kept so that the security journal can
    #: record what exactly they agreed to, not only the action's name.
    preview: str = ""

    def expired(self, now=None):
        return (now or time.time()) >= self.expires_at

    def to_dict(self):
        return {"id": self.id, "tool": self.tool,
                "fingerprint": self.fingerprint,
                "issued_at": self.issued_at, "expires_at": self.expires_at,
                "scope": self.scope, "preview": self.preview}


class ConfirmationLedger:
    """
    The confirmations that have been issued.

    Lives in the core: the decision on whether an action is confirmed must
    not be taken on the shell's side, or it can be circumvented from the
    interface.
    """

    def __init__(self, ttl=DEFAULT_TTL, clock=time.time):
        self._ttl = ttl
        #: The clock is passed in from outside for the same reason as
        #: everywhere in the core: a deadline must be checkable rather than
        #: waited out. But there is a second reason here, and a weightier
        #: one. The permission channel (4.0-D12) counts its own waiting
        #: window on a clock of its own and passes the remaining time here.
        #: While the ledger ran on system time and the channel on its own,
        #: these were two different scales in one loop: a deadline computed
        #: on one was checked on the other. The conformance suite noticed
        #: it, where an expired confirmation passed without trouble.
        self._clock = clock
        self._items = {}
        self._lock = threading.RLock()

    # ---------- issuing ----------
    def issue(self, tool_name, args=None, ttl=None, scope=ONCE, preview=""):
        """Issue a confirmation for a particular call."""
        if scope not in SCOPES:
            raise ValueError(f"неизвестная область: {scope!r}")
        now = self._clock()
        confirmation = Confirmation(
            id=secrets.token_urlsafe(12),
            tool=tool_name,
            fingerprint=fingerprint(tool_name, args),
            issued_at=now,
            expires_at=now + (self._ttl if ttl is None else ttl),
            scope=scope,
            preview=preview,
        )
        with self._lock:
            self._items[confirmation.id] = confirmation
        return confirmation

    # ---------- presenting ----------
    def redeem(self, confirmation_id, tool_name, args=None, now=None):
        """
        Accept a confirmation and burn it.

        Returns a Confirmation or raises a ConfirmationError. The error
        codes differ deliberately: "not presented", "not found", "expired"
        and "not for this action" are four different situations, and a
        person has to be told different things.
        """
        if not confirmation_id:
            raise ConfirmationError(
                "действие требует подтверждения",
                "confirmation.required", {"tool": tool_name})

        with self._lock:
            confirmation = self._items.get(confirmation_id)
            if confirmation is None:
                raise ConfirmationError(
                    "подтверждение не найдено или уже использовано",
                    "confirmation.invalid", {"tool": tool_name})

            if confirmation.expired(now if now is not None else self._clock()):
                del self._items[confirmation_id]
                raise ConfirmationError(
                    "подтверждение просрочено",
                    "confirmation.expired", {"tool": tool_name})

            if confirmation.tool != tool_name:
                raise ConfirmationError(
                    "подтверждение выдано на другое действие",
                    "confirmation.invalid",
                    {"tool": tool_name, "confirmed": confirmation.tool})

            if confirmation.fingerprint != fingerprint(tool_name, args):
                raise ConfirmationError(
                    "подтверждение выдано на другие аргументы",
                    "confirmation.invalid", {"tool": tool_name})

            # A one-time one burns up; an "until" one stays valid until expires_at.
            if confirmation.scope == ONCE:
                del self._items[confirmation_id]

        return confirmation

    # ---------- maintenance ----------
    def revoke(self, confirmation_id):
        with self._lock:
            return self._items.pop(confirmation_id, None) is not None

    def revoke_all(self):
        """Revoke every one issued — the 5.0-D08 kill switch will come here."""
        with self._lock:
            count = len(self._items)
            self._items.clear()
            return count

    def purge_expired(self, now=None):
        now = self._clock() if now is None else now
        with self._lock:
            dead = [i for i, c in self._items.items() if c.expired(now)]
            for i in dead:
                del self._items[i]
            return len(dead)

    def pending(self):
        with self._lock:
            return len(self._items)
