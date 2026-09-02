"""
Долгие задачи и кооперативная отмена.

Задачи плана `4.0-D09` (жизненный цикл) и `4.0-D10` (отмена);
спецификация, §9.

Кодинг-задача в RinaNeuro идёт минутами. Модель «запрос — ответ» этого не
выражает: у неё есть только «ещё не ответил» и «ответил», а между ними лежит
всё интересное — сколько сделано, что уже получилось, можно ли остановить.
Поэтому жизненный цикл закладывается сейчас, пока цена нулевая, хотя в 4.0
долгих задач нет.

    accepted ──> running ──┬──> done
                           ├──> failed
                           └──> cancelled
                  (progress, partial — сколько угодно раз)

**Ровно одно из `done`/`failed`/`cancelled` завершает задачу.** Это главный
инвариант, и он проверяется, а не подразумевается: сторона, получившая два
финальных события, не знает, какому верить, а получившая ноль — ждёт вечно.
После финального события любое другое сообщение задачи — дефект отправителя
(`protocol.invalid_state`).

**Отмена — три шага, а не один.**

    task.cancel ──> ответ {accepted} ──> … фактическая остановка … ──> task.cancelled

Подтверждение получения запроса — не то же самое, что остановка, и путать их
нельзя: отмена, которая молча ничего не делает, хуже отсутствия отмены.
Отмена кооперативная: задача сама замечает просьбу и останавливается там, где
это безопасно, — прервать чужую работу в произвольной точке значит оставить
после себя недописанный файл.

**Гонка описана и разрешена.** Если задача завершилась сама раньше, чем
отмена доехала, приходит `done`, а `task.cancelled` не приходит вовсе.
Спецификация требует, чтобы запрашивающая сторона это выдержала; здесь та же
гонка честно отражена в ответе на `task.cancel` — `accepted: false` вместе с
текущим состоянием. Ответ `true`, за которым никогда не последует
`task.cancelled`, был бы обещанием, которого никто не собирался выполнять.
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


#: Состояния, из которых нет выхода.
FINAL = (TaskState.DONE, TaskState.FAILED, TaskState.CANCELLED)

#: Что отвечает `task.cancel` про задачу, о которой ничего не известно.
STATUS_UNKNOWN = "unknown"


@dataclass
class Task:
    """
    Одна долгая задача на стороне, которая её выполняет.

    Задача не знает ни о канале, ни о том, кто её слушает: она возвращает
    готовые сообщения, а отправляет их вызывающий. Так её можно прогнать в
    тесте без транспорта — и так же её прогонят conformance-тесты `4.0-D16`.
    """

    id: str
    ids: Any                      # IdGenerator: номера сообщений
    state: str = TaskState.ACCEPTED
    cancel_requested: bool = False
    events: list[Envelope] = field(default_factory=list)

    # -- ответ на запрос, породивший задачу ----------------------------------

    def accepted_payload(self) -> dict[str, Any]:
        """Тело ответа на запрос: задача принята, работа началась."""
        return {"task_id": self.id, "status": TaskState.ACCEPTED}

    # -- ход работы ----------------------------------------------------------

    def start(self) -> None:
        self._require_live("начать")
        self.state = TaskState.RUNNING

    def progress(self, note: str, fraction: float | None = None) -> Envelope:
        """
        Сообщить о продвижении.

        Пояснение обязательно, доля — нет: доля известна не всякой задаче, а
        прогресс без слов не сообщает ничего, кроме того, что процесс жив.
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

    # -- завершение ----------------------------------------------------------

    def done(self, result: Any) -> Envelope:
        self._finish(TaskState.DONE, "завершить")
        return self._emit("task.done", {"task_id": self.id, "result": result})

    def failed(self, error) -> Envelope:
        """`error` — `ProtocolError` либо готовый словарь по §5."""
        self._finish(TaskState.FAILED, "завалить")
        payload = error.to_payload() if hasattr(error, "to_payload") else error
        return self._emit("task.failed",
                          {"task_id": self.id, "error": payload})

    def cancelled(self) -> Envelope:
        """
        Задача действительно остановилась.

        Отправляется только после того, как работа прекращена, — в этом весь
        смысл третьего шага. Отправить его вместо подтверждения получения
        значит соврать о том, что уже ничего не выполняется.
        """
        self._finish(TaskState.CANCELLED, "отменить")
        return self._emit("task.cancelled", {"task_id": self.id})

    # -- отмена --------------------------------------------------------------

    def request_cancel(self) -> dict[str, Any]:
        """
        Принять просьбу об отмене. Возвращает тело ответа на `task.cancel`.

        Не останавливает задачу: остановиться она обязана сама, заметив флаг.
        """
        if self.state in FINAL:
            return {"accepted": False, "status": self.state}
        self.cancel_requested = True
        return {"accepted": True, "status": self.state}

    @property
    def finished(self) -> bool:
        return self.state in FINAL

    # -- внутреннее ----------------------------------------------------------

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
    Живые задачи стороны.

    Завершённые задачи не удаляются сразу: `task.cancel` на только что
    завершённую задачу — обычная гонка, а не дефект, и ответить на неё
    «такой задачи нет» значило бы отправить отладку по ложному следу.
    Хранится последний известный итог, чего достаточно, чтобы отличить
    «опоздал» от «ошибся идентификатором».
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
        Забыть все задачи — при обрыве связи (`4.0-D14`).

        Именно забыть, а не отменить: отменить значит сообщить о
        `task.cancelled`, а сообщать некому — собеседника нет.
        """
        count = len(self.tasks)
        self.tasks.clear()
        return count

    def get(self, task_id: str) -> Task | None:
        return self.tasks.get(task_id)

    def cancel(self, task_id: str) -> dict[str, Any]:
        """
        Обработать `task.cancel`. Тело ответа — по §9.

        Неизвестный идентификатор не ошибка: чаще всего это задача, о которой
        сторона уже забыла. Ответ говорит правду — принять нечего.
        """
        task = self.tasks.get(task_id)
        if task is None:
            return {"accepted": False, "status": STATUS_UNKNOWN}
        return task.request_cancel()


def run(task: Task, steps: int, clock: Callable[[], float],
        advance: Callable[[float], None], *, seconds: float,
        partial_every: int = 0) -> list[Envelope]:
    """
    Прогнать задачу по шагам — заглушка §15.7 без ожидания в реальном времени.

    Часы передаются снаружи: требование спецификации говорит о задаче на
    шестьдесят секунд, и проверять его настоящим ожиданием значило бы держать
    проверку минуту ради формы, которая от длительности не зависит. Поддельные
    часы дают ту же последовательность событий за миллисекунды.

    Отмена проверяется **перед** каждым шагом: задача, замечающая просьбу
    только после последнего шага, формально кооперативна и практически
    бесполезна.
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
