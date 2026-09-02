"""
Контур подтверждения опасных действий.

Задача плана 4.0-C05. В 3.1.0 подтверждение жило словарём `pending` внутри
ядра: без идентификатора, без срока и без однократности. Проверить, что
опасное действие подтверждено, можно было только доверившись порядку вызовов —
то есть никак.

Здесь подтверждение становится предметом, который можно предъявить:

    confirmation_id   выдан на конкретный вызов
    срок              просроченное не принимается
    однократность     предъявленное сгорает

Три свойства, каждое из которых закрывает свой способ ошибиться.

**Привязка к аргументам, а не только к инструменту.** Согласие на «усыпить»
нельзя предъявить для «выключить»: это один инструмент `power_action` с
разными аргументами, и без отпечатка аргументов подмена прошла бы. Человек
подтверждает то, что ему показали, а не имя функции.

**Однократность.** Иначе одно согласие годилось бы до истечения срока для
любого числа вызовов — то есть «выключи компьютер», подтверждённое однажды,
выключало бы его и на второй раз, когда фраза распозналась случайно.

Qt здесь нет: модуль лежит в ядре.
"""

import hashlib
import json
import secrets
import threading
import time
from dataclasses import dataclass


#: Сколько живёт выданное подтверждение. Совпадает со сроком незакрытого
#: вопроса (core/dialog.py): и то и другое — окно, в течение которого ответ
#: человека ещё относится к заданному вопросу.
DEFAULT_TTL = 60

#: Область действия.
#:
#: Их две, а не три, как было записано в §11 спецификации. «До конца сессии»
#: убрано не из осторожности, а потому что отдельного механизма под него нет:
#: §13 прямо говорит, что выданные разрешения переподключение не переживают,
#: то есть сессия и есть верхняя граница для любой области. Третье имя для
#: того же поведения — приглашение считать, будто оно другое.
#:
#: Прежнее имя SESSION описывало ровно нынешнее UNTIL: подтверждение
#: оставалось годным до истечения срока, а вовсе не до конца сессии. Имя,
#: обещающее не то, что делает код, — заготовка будущей ошибки.
ONCE = "once"          # сгорает при первом предъявлении
UNTIL = "until"        # годно до expires_at, сколько угодно раз
SCOPES = (ONCE, UNTIL)


class ConfirmationError(Exception):
    """Подтверждение не принято. Несёт код для протокола."""

    def __init__(self, message, code, details=None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details or {}


def fingerprint(tool_name, args):
    """
    Отпечаток вызова: инструмент плюс аргументы.

    Считается от канонической записи, чтобы порядок ключей не менял
    результат — иначе подтверждение переставало бы подходить само себе.
    """
    payload = json.dumps({"tool": tool_name, "args": args or {}},
                         sort_keys=True, ensure_ascii=False,
                         separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


@dataclass(frozen=True)
class Confirmation:
    """Выданное разрешение на один конкретный вызов."""

    id: str
    tool: str
    fingerprint: str
    issued_at: float
    expires_at: float
    scope: str = ONCE
    #: Что показали человеку. Хранится, чтобы журнал безопасности мог
    #: записать, на что именно он согласился, а не только имя действия.
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
    Выданные подтверждения.

    Живёт в ядре: решение о том, подтверждено ли действие, не должно
    приниматься на стороне оболочки, иначе его можно обойти со стороны
    интерфейса.
    """

    def __init__(self, ttl=DEFAULT_TTL, clock=time.time):
        self._ttl = ttl
        #: Часы передаются снаружи по той же причине, что и всюду в ядре:
        #: срок надо уметь проверить, а не переждать. Но здесь есть и вторая,
        #: важнее. Канал разрешений (4.0-D12) считает своё окно ожидания по
        #: собственным часам и передаёт сюда остаток срока. Пока журнал жил по
        #: системному времени, а канал — по своим, это были две разные шкалы в
        #: одном контуре: срок, вычисленный на одной, проверялся на другой.
        #: Заметил это conformance-набор, где просроченное подтверждение
        #: спокойно прошло.
        self._clock = clock
        self._items = {}
        self._lock = threading.RLock()

    # ---------- выдача ----------
    def issue(self, tool_name, args=None, ttl=None, scope=ONCE, preview=""):
        """Выдать подтверждение на конкретный вызов."""
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

    # ---------- предъявление ----------
    def redeem(self, confirmation_id, tool_name, args=None, now=None):
        """
        Принять подтверждение и погасить его.

        Возвращает Confirmation или бросает ConfirmationError. Коды ошибок
        разные намеренно: «не предъявлено», «не найдено», «просрочено» и «не
        от этого действия» — четыре разные ситуации, и человеку нужно
        сказать разное.
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

            # Однократное сгорает; «до срока» остаётся годным до expires_at.
            if confirmation.scope == ONCE:
                del self._items[confirmation_id]

        return confirmation

    # ---------- обслуживание ----------
    def revoke(self, confirmation_id):
        with self._lock:
            return self._items.pop(confirmation_id, None) is not None

    def revoke_all(self):
        """Снять все выданные — сюда придёт kill-switch из 5.0-D08."""
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
