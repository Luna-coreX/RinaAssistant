"""
Канал разрешений: ядро просит, оболочка спрашивает человека.

Задача плана `4.0-D12`; спецификация, §11. Опирается на контур подтверждений
`4.0-C05` (`core/confirmations.py`).

Ядро не может выполнить опасное действие само и не умеет показывать окна. Оно
сообщает о намерении — что произойдёт, почему и на какой срок, — оболочка
показывает это человеку и возвращает решение.

**Идентификатор подтверждения выпускает ядро, а не оболочка.** Спецификация
§11 в первой редакции возвращала `confirmation_id` в ответе оболочки, то есть
оболочка его и порождала. Это прямо противоречило `4.0-C05`, где записано:
решение о том, подтверждено ли действие, не должно приниматься на стороне
оболочки, иначе его можно обойти со стороны интерфейса. Оболочка, выпускающая
идентификаторы, может выпустить любой, и ядру нечем отличить настоящий от
выдуманного — а вся однократность и привязка к аргументам держатся ровно на
том, что идентификатор выдан ядром под конкретный вызов.

Поэтому здесь: ядро заводит **просьбу** с собственным номером, оболочка
отвечает «да» или «нет», и только после «да» ядро выписывает подтверждение.
Оболочка не может создать подтверждение — она может лишь разрешить создать.

**Отказ по умолчанию.** Просьба, на которую не ответили в срок, считается
отклонённой. Не «ждём дальше» и не «раз молчит, значит согласен»: молчание
может означать, что окна вообще никто не увидел.

**Область `session` из спецификации убрана.** Осталось две: `once` — одно
исполнение, `until` — до истечения срока. Третья описывала то же, что
`until`, потому что §13 и так говорит: выданные разрешения переподключение не
переживают, то есть сессия — верхняя граница любой области.

**Опасному действию `until` не выдаётся.** Разрешение, действующее полчаса на
выключение компьютера, — это и есть тот случай, ради которого подтверждение
заводили. Если оболочка попросит такую область, ядро понижает её до `once` и
говорит об этом в ответе: человек согласился на это действие, и терять его
согласие незачем, а вот расширять — незачем тем более.
"""

import secrets
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from core.confirmations import ONCE, SCOPES, UNTIL, ConfirmationLedger
from core.permissions import dangerous
from core.wire.errors import ERROR_INVALID_PAYLOAD, ERROR_INVALID_STATE, fault

#: Сколько ждём ответа человека, если ядро не назвало срок.
DEFAULT_TTL = 60


@dataclass(frozen=True)
class Ask:
    """Просьба, отправленная оболочке и ещё не получившая ответа."""

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
        Что уходит в канал (§11).

        Аргументы вызова наружу не идут: оболочке нужно показать человеку
        `preview` — что именно произойдёт словами, — а не сериализованный
        вызов. Отпечаток аргументов остаётся в ядре, там же, где проверяется.
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
    Ядерная сторона канала разрешений.

    Хранит незакрытые просьбы и выписывает подтверждения по ответам оболочки.
    Часы передаются снаружи, чтобы срок можно было проверить, а не переждать.
    """

    def __init__(self, ledger: ConfirmationLedger | None = None,
                 clock: Callable[[], float] = time.time):
        #: Журнал по умолчанию заводится **на тех же часах**. Разные шкалы
        #: времени у канала и у журнала — это срок, вычисленный на одной и
        #: проверяемый на другой; conformance-набор поймал ровно это.
        #: Переданный снаружи журнал обязан идти по тому же времени.
        self.ledger = ledger or ConfirmationLedger(clock=clock)
        self._clock = clock
        self._pending: dict[str, Ask] = {}

    # -- ядро просит ---------------------------------------------------------

    def ask(self, tool: str, args: dict[str, Any] | None = None, *,
            permission: str, reason: str, preview: str,
            ttl: int = DEFAULT_TTL) -> Ask:
        """
        Завести просьбу. Возвращает её; отправляет вызывающий.

        `preview` обязателен: §11 требует показать, что именно произойдёт, а
        не только название действия. «Выключить компьютер» и «Компьютер будет
        выключен немедленно» — разные сообщения, и второе человек успевает
        осознать.
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

    # -- оболочка ответила ---------------------------------------------------

    def resolve(self, request_id: str, granted: bool,
                scope: str = ONCE) -> dict[str, Any]:
        """
        Принять ответ оболочки и, если разрешено, выписать подтверждение.

        Возвращает тело ответа по §11. Просьба закрывается в любом случае:
        ответить на неё дважды нельзя, иначе «нет» можно было бы переиграть.
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
        Закрыть просьбы, на которые не ответили. Возвращает сколько.

        Вызывается по таймеру: просьба, о которой все забыли, не должна
        оставаться открытой — иначе поздний ответ разрешит действие, о
        котором человек уже не помнит.
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
        Забыть всё: незакрытые просьбы и выданные подтверждения.

        Нужно при обрыве связи (`4.0-D14`). Разрешение, выданное до обрыва,
        относится к разговору, которого больше нет: неизвестно, что успело
        произойти на той стороне, и человек, соглашавшийся минуту назад,
        соглашался не на это.
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
