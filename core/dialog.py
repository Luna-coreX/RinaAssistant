"""
The assistant's unclosed questions: explicit transitions, serialisable state.

Plan item 4.0-B03. This used to be a `self._pending` dict inside the core:
the transitions lived in three places at once, the state could neither be
saved nor shown, and the list of options held AppEntry objects — that is,
such a state would not have travelled over the protocol at all.

Rina asks questions of three kinds, and they are all built the same way: we
asked, we are waiting for an answer, and after a minute the question goes
stale.

    choose_app       which of several programs to launch
    confirm_action   confirm a dangerous system action
    confirm_command  confirm a dangerous user command

3.1.0's behaviour is reproduced literally, including the non-obvious part:
**any unrecognised line withdraws the question** (see
docs/INVENTORY-3.1.0.md, §6). Say "shut down the computer", then something
unrelated, then "yes" — and nothing happens. For a dangerous action that is
the cautious side of the mistake, for choosing a program it is a lost
question; it must not be changed here, or the golden suite will show a
divergence where none was intended.

There is no Qt here: the module lies in the core.
"""

import time
from dataclasses import dataclass, field, replace


#: After how many seconds a question that was asked counts as stale.
TTL_SECONDS = 60

CHOOSE_APP = "choose_app"
CONFIRM_ACTION = "confirm_action"
CONFIRM_COMMAND = "confirm_command"

KINDS = (CHOOSE_APP, CONFIRM_ACTION, CONFIRM_COMMAND)


@dataclass(frozen=True)
class Question:
    """
    A question that was asked. Serialisable values only.

    The options are kept as dicts rather than AppEntry objects: the state is
    obliged to survive being written to a file and travelling over the
    protocol. Restoring the object from a dict is something the program
    index can do itself.
    """

    kind: str
    asked_at: float = field(default_factory=time.time)
    #: for confirm_action
    action: str = ""
    #: for confirm_command
    command_id: str = ""
    #: for choose_app — a list of dicts of the form AppEntry.to_dict()
    options: tuple = ()
    #: what was being looked for when the question arose
    query: str = ""
    #: the confirmation issued for a dangerous action (4.0-C05).
    #: Kept in the question, because a person's consent applies to a
    #: particular call rather than to the fact that a question was once asked.
    confirmation_id: str = ""

    def __post_init__(self):
        if self.kind not in KINDS:
            raise ValueError(f"неизвестный вид вопроса: {self.kind!r}")
        object.__setattr__(self, "options", tuple(self.options))

    def expired(self, now=None):
        return (now or time.time()) - self.asked_at > TTL_SECONDS

    def entries(self):
        """The options back as index objects."""
        from voice.app_index import AppEntry

        return [AppEntry.from_dict(o) for o in self.options]

    def to_dict(self):
        return {"kind": self.kind, "asked_at": self.asked_at,
                "action": self.action, "command_id": self.command_id,
                "options": [dict(o) for o in self.options],
                "query": self.query,
                "confirmation_id": self.confirmation_id}

    @classmethod
    def from_dict(cls, data):
        return cls(kind=data["kind"],
                   asked_at=float(data.get("asked_at", 0.0)),
                   action=str(data.get("action", "")),
                   command_id=str(data.get("command_id", "")),
                   options=tuple(data.get("options") or ()),
                   query=str(data.get("query", "")),
                   confirmation_id=str(data.get("confirmation_id", "")))

    @classmethod
    def choose_app(cls, options, query=""):
        """options is a list of AppEntry."""
        return cls(kind=CHOOSE_APP, query=query,
                   options=tuple(e.to_dict() for e in options))

    @classmethod
    def confirm_action(cls, action, confirmation_id=""):
        return cls(kind=CONFIRM_ACTION, action=action,
                   confirmation_id=confirmation_id)

    @classmethod
    def confirm_command(cls, command_id, confirmation_id=""):
        return cls(kind=CONFIRM_COMMAND, command_id=command_id,
                   confirmation_id=confirmation_id)


class Dialog:
    """
    The unclosed question and the transitions around it.

    There are exactly three transitions, and there must be no others:

        ask      — a question was asked
        answered — it was answered, the question is withdrawn
        dropped  — the question was withdrawn without an answer (stale or
                   interrupted)
    """

    def __init__(self, question=None):
        self._question = question

    # ---------- reading ----------
    def current(self, now=None):
        """The question in force, or None. A stale one is withdrawn here and now."""
        if self._question is None:
            return None
        if self._question.expired(now):
            self._question = None
            return None
        return self._question

    @property
    def pending(self):
        return self.current() is not None

    # ---------- transitions ----------
    def ask(self, question):
        self._question = question
        return question

    def answered(self):
        """The question was closed by an answer."""
        self._question = None

    def dropped(self):
        """
        The question was withdrawn without an answer.

        That is how 3.1.0 behaves on any unrecognised line. A transition
        separate from `answered`, because these are different events: one
        means "we understood", the other "we forgot".
        """
        self._question = None

    # ---------- state ----------
    def to_dict(self):
        return {"question": self._question.to_dict() if self._question
                else None}

    @classmethod
    def from_dict(cls, data):
        question = (data or {}).get("question")
        return cls(Question.from_dict(question) if question else None)

    def __repr__(self):
        q = self._question
        return f"<Dialog {q.kind if q else 'пусто'}>"
