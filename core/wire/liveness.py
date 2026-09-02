"""
Живость, обрыв, переподключение.

Задача плана `4.0-D14`; спецификация, §13.

В одном процессе смерть половины программы не бывает: падает всё сразу, и это
видно. В двух — сторона может умереть молча, и вторая будет ждать ответа,
которого не будет никогда. Окно, которое ждёт мёртвое ядро, выглядит зависшим,
и человек не отличит его от медленного.

**Молчание — не признак смерти.** Признак смерти — молчание в ответ на прямой
вопрос. Поэтому `ping` шлётся только после паузы, а мёртвой сторона считается
после трёх неотвеченных подряд: одна потеря может случиться от чего угодно,
три подряд — уже закономерность.

**Любое сообщение считается за понг.** Занятый канал пинговать незачем: если
собеседник только что прислал событие, он жив, и лишний вопрос — трата на
пустом месте. Отсюда счётчик тишины, а не таймер по расписанию.

**Что переживает переподключение, а что нет.** Настройки, команды, история,
напоминания, плагины лежат в хранилище и переживают. Не переживают:
незакрытый уточняющий вопрос, открытые потоки, выданные разрешения,
незавершённые задачи. Это не упрощение реализации, а решение: после обрыва
неизвестно, что успело произойти на той стороне, и разрешение, выданное до
обрыва, относится к разговору, которого больше нет.

Поэтому состояние после рукопожатия **собирается заново запросами, а не
восстанавливается по памяти**. Память пережившей стороны — не источник правды
о том, что происходит у собеседника.
"""

import time
from dataclasses import dataclass, field
from typing import Any, Callable

#: После какой тишины спрашивать «жив ли» (§13).
SILENCE = 5.0

#: Сколько неотвеченных вопросов подряд считать смертью.
MISSED_LIMIT = 3


class Liveness:
    """
    Счётчик тишины и неотвеченных вопросов на одной стороне.

    Не шлёт ничего сам: решает, пора ли, и считает. Отправку делает тот, у
    кого есть канал, — так эту логику можно проверить на поддельных часах, не
    поднимая транспорта.
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
        Пришло любое сообщение.

        Считается за ответ: собеседник, приславший событие, жив не менее
        убедительно, чем приславший понг.
        """
        self.last_seen = self._clock() if now is None else now
        self.missed = 0
        self._awaiting = False

    def note_pong(self, now: float | None = None) -> None:
        self.note_traffic(now)

    def silent_for(self, now: float | None = None) -> float:
        return (self._clock() if now is None else now) - self.last_seen

    def due(self, now: float | None = None) -> bool:
        """Пора ли слать `ping`."""
        return self.silent_for(now) >= self._silence

    def sent_ping(self, now: float | None = None) -> None:
        """
        Вопрос задан и пока не отвечен.

        Второй `ping` без ответа на первый — не удвоение вопроса, а второй
        неотвеченный: именно они и считаются.
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
    То, что обрыв уносит с собой (§13).

    Собрано в одном месте намеренно. Разложенное по владельцам, оно
    сбрасывалось бы в нескольких местах, и однажды где-то не сбросилось бы —
    причём незаметно: пережившее обрыв разрешение выглядит как обычное
    разрешение, и обнаружится оно только тем, что сработает.
    """

    permissions: Any = None      # PermissionChannel
    tasks: Any = None            # tasks.Registry
    data_streams: Any = None     # data.DataSender
    text_streams: Any = None     # events.StreamSender
    session: Any = None          # handshake.Session
    also: list[Callable[[], int]] = field(default_factory=list)

    def snapshot(self) -> dict[str, int]:
        """Сколько всего живёт сейчас — для журнала и для проверки."""
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
        Сбросить всё, что не переживает обрыв. Возвращает, чего сколько было.

        Задачи не «отменяются», а забываются: отменить — значит сообщить о
        `task.cancelled`, а сообщать некому и незачем, собеседника нет. Тот,
        кто переподключится, спросит заново.
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
