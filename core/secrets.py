"""
Secrets: a plugin's token, a key to a model's service (`4.0-H11`).

**Not in the settings.** The settings are a file of plain text that goes
into the export on the privacy page and is meant to be readable; a password
to a mailbox cannot live there. Secrets are kept in the Windows Credential
Manager, encrypted with the person's own account — by the shell, which
owns the machine (ADR 0009). This module asks it, by name.

**The owner is given here, never by a plugin.** `core` for Rina's own, and
`plugin:<id>` for a plugin's, filled in by the core from the plugin that is
asking. A plugin names only *what* it keeps; whose it is, it cannot say, so
it cannot read another plugin's token.

**No value is written anywhere but the store.** Not to the journal, not to
the settings, not to the export: what can be listed is the names, for the
privacy page's "a sign-in is kept".

Without a shell — the checks, the 3.1.0 path — there is nowhere to keep a
secret, and that is a refusal (`SecretsUnavailable`) rather than a file of
plain text written as a fallback.
"""
import re

from core.logging_setup import get_logger

log = get_logger("secrets")

#: What a name may be: a word of letters, digits, dots, dashes, underscores.
NAME = re.compile(r"^[\w.\-]{1,64}$")

#: The owner of Rina's own secrets.
CORE = "core"


class SecretsUnavailable(Exception):
    """There is nowhere to keep a secret: no shell, or it does not answer."""


def plugin_owner(plugin_id):
    """The owner a plugin's secrets are kept under."""
    return f"plugin:{plugin_id}"


class SecretStore:
    """
    The secrets, through the shell.

    `ask(method, payload) -> dict` is the shell's answer to `secrets.*`;
    None — there is no shell.
    """

    def __init__(self, ask=None):
        self._ask = ask

    def available(self):
        return self._ask is not None

    def _call(self, method, payload):
        if self._ask is None:
            raise SecretsUnavailable("секреты хранит оболочка, а её нет")
        try:
            return dict(self._ask(method, payload) or {})
        except Exception as exc:                        # noqa: BLE001
            # The reason, never the payload: the payload may be the secret.
            log.warning("Хранилище секретов не ответило: %s", type(exc).__name__)
            raise SecretsUnavailable(str(type(exc).__name__)) from exc

    @staticmethod
    def _check(owner, name):
        if not NAME.match(str(name or "")):
            raise ValueError(f"недопустимое имя секрета: {name!r}")
        if owner != CORE and not str(owner).startswith("plugin:"):
            raise ValueError(f"недопустимый владелец секрета: {owner!r}")

    def get(self, owner, name):
        """The secret, or None when nothing is kept under that name."""
        self._check(owner, name)
        answer = self._call("secrets.get", {"owner": owner, "name": name})
        return str(answer.get("value", "")) if answer.get("found") else None

    def set(self, owner, name, value):
        """Keep a secret; raises `SecretsUnavailable` if it was not kept."""
        self._check(owner, name)
        answer = self._call("secrets.set", {"owner": owner, "name": name,
                                            "value": str(value)})
        if not answer.get("ok"):
            raise SecretsUnavailable(str(answer.get("reason") or "not kept"))
        log.info("Секрет сохранён: %s / %s", owner, name)

    def delete(self, owner, name=""):
        """Forget one secret, or every one of an owner's. How many went."""
        if name:
            self._check(owner, name)
        else:
            self._check(owner, "all")
        answer = self._call("secrets.delete", {"owner": owner, "name": name})
        gone = int(answer.get("deleted") or 0)
        if gone:
            log.info("Секретов забыто: %d (%s)", gone, owner)
        return gone

    def names(self):
        """What is kept: (owner, name) pairs, never a value."""
        answer = self._call("secrets.list", {})
        return [(str(one.get("owner", "")), str(one.get("name", "")))
                for one in answer.get("items") or []
                if isinstance(one, dict)]
