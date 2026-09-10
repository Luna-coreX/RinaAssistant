# -*- coding: utf-8 -*-
"""
Things to do: what waits, rather than what fires.

Plan item `4.0b-A13`.

**Why these are not reminders.** A reminder **fires**: it has a moment or an
occasion, and it announces itself. A thing to do **waits**: it has no
deadline and lies there until a person closes it. Merging them into one list
means either making every thing to do pretend to be a reminder for a while,
or creating reminders that will never fire — and `4.0b-A03` avoids the
second deliberately, for the same reason: a reminder that did not fire shows
nothing of itself.

There is a connection, and it goes one way: a thing to do can be given a
reminder, and then an ordinary `4.0-E05` entry appears beside it. Ordinary —
that is, with a deadline or an occasion, living in its own store and firing
by the common rules. No second grade of reminder is created.

There is no Qt here: the module lies in the core.
"""

import time
import uuid

from core.i18n import t as tr
from voice.textmatch import normalize


#: What a request to write something down begins with.
#:
#: "напомни" is not here, and that is not an omission: the word belongs to
#: reminders, and giving it to two different things means making a person
#: guess which they will get.
ADD_WORDS = ("запиши", "добавь в дела", "добавь дело", "новое дело",
             "надо", "нужно сделать", "не забыть")

#: A request to see the list.
LIST_WORDS = ("какие дела", "мои дела", "список дел", "что мне надо",
              "что я должен", "что я должна")

#: A request to close something.
DONE_WORDS = ("сделал", "сделала", "готово", "выполнил", "выполнила",
              "закрой дело", "убери дело")


def parse(text):
    """
    A phrase -> what to do about the list, or None.

    Returns `(what, rest)`: `add` with the text, `list` with nothing, `done`
    with whatever the person named.

    The parsing is pure: it knows nothing about what is already on the list.
    Finding the named one among them is the job of whoever holds the list.
    """
    if not text:
        return None
    low = normalize(text)
    if not low:
        return None

    for word in LIST_WORDS:
        if word in low:
            return "list", ""

    for word in DONE_WORDS:
        if low.startswith(word) or f" {word}" in low:
            rest = low.split(word, 1)[1].strip()
            return "done", rest

    for word in ADD_WORDS:
        if low.startswith(word):
            # "запиши" with nothing after it is handed on as it is, with
            # empty text.
            #
            # Refusing it right here was tempting and made things worse: an
            # unparsed phrase goes on down the stages and ends in a web
            # search for "запиши". A person who started to speak and thought
            # better of it got a browser window instead of "I did not catch
            # what to write down". Nothing empty is stored — the store sees
            # to that — and the answer belongs to whoever knows what was
            # being asked.
            return "add", low[len(word):].strip()
    return None


class TodoStore:
    """
    The list in the settings, beside everything else that outlives a run.

    The store is passed in from outside — the very one the core works with.
    The module takes no singleton of its own: two cores in one process would
    silently share the list, and a check with a stand-in store would write
    into the person's real file. Exactly what `4.0-B05` and `4.0-B06` were
    for.
    """

    def __init__(self, settings):
        self._settings = settings

    def all(self, done=None):
        """
        The list, brought to the expected form.

        `done=None` is everything; `False` only the open ones; `True` only
        the closed. A spoiled entry is discarded here rather than in every
        place that shows the list: the file may have been edited by hand.
        """
        clean = []
        for item in (self._settings.get("todo", []) or []):
            if not isinstance(item, dict):
                continue
            text = str(item.get("text", "")).strip()
            if not text:
                continue
            closed = bool(item.get("done", False))
            if done is not None and closed != done:
                continue
            clean.append({
                "id": str(item.get("id", "")) or uuid.uuid4().hex[:8],
                "text": text,
                "done": closed,
                "created": float(item.get("created", 0) or 0),
                # The reminder's number, if one was asked for. The reminder
                # itself lives in its own store: this is only a reference.
                "reminder_id": str(item.get("reminder_id", "")),
            })
        return clean

    def add(self, text):
        """Write something down. Returns what was written."""
        text = (text or "").strip()
        if not text:
            return None
        item = {
            "id": uuid.uuid4().hex[:8],
            "text": text,
            "done": False,
            "created": time.time(),
            "reminder_id": "",
        }
        with self._settings.transaction():
            items = self.all()
            items.append(item)
            self._save(items)
        return item

    def close(self, todo_id):
        """Mark it done. True if there was such a thing."""
        return self._change(todo_id, done=True)

    def reopen(self, todo_id):
        """Changed their mind: it is waiting again."""
        return self._change(todo_id, done=False)

    def remove(self, todo_id):
        """Remove it for good. True if there was anything to remove."""
        with self._settings.transaction():
            items = self.all()
            left = [i for i in items if i["id"] != todo_id]
            if len(left) == len(items):
                return False
            self._save(left)
        return True

    def bind_reminder(self, todo_id, reminder_id):
        """
        Tie a thing to do to a reminder about it.

        By reference, not by copy: the reminder lives its own life — it can
        be cancelled from the reminder list — and keeping its deadline here
        would create a second source of truth about when it fires.
        """
        return self._change(todo_id, reminder_id=str(reminder_id))

    def find(self, said):
        """
        The thing the person named in words.

        An exact match, then a substring. Nothing cleverer: the list is
        short, and being wrong here means closing the wrong thing — which
        the person will not notice, because a closed thing simply leaves the
        list.
        """
        said = normalize(said or "")
        if not said:
            return None
        open_ones = self.all(done=False)
        for item in open_ones:
            if normalize(item["text"]) == said:
                return item
        for item in open_ones:
            if said in normalize(item["text"]):
                return item
        return None

    def _change(self, todo_id, **fields):
        with self._settings.transaction():
            items = self.all()
            for item in items:
                if item["id"] == todo_id:
                    item.update(fields)
                    self._save(items)
                    return True
        return False

    def _save(self, items):
        """
        Write the list as a whole — under a transaction.

        Both the person adding something and the shell closing it arrive
        here: two paths, one write. The same rule as for reminders and for
        the user's own commands.
        """
        self._settings.set("todo", items)
        self._settings.save()


def say_list(items):
    """The list in words — for speaking aloud."""
    if not items:
        return tr("Дел нет.")
    if len(items) == 1:
        return tr("Одно дело: {text}.", text=items[0]["text"])
    listed = ", ".join(item["text"] for item in items[:5])
    if len(items) > 5:
        return tr("Дел {count}, первые пять: {listed}.",
                  count=len(items), listed=listed)
    return tr("Дел {count}: {listed}.", count=len(items), listed=listed)
