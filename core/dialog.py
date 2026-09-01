"""
Незакрытые вопросы ассистента: явные переходы, сериализуемое состояние.

Задача плана 4.0-B03. Раньше это был словарь `self._pending` внутри ядра:
переходы жили в трёх местах разом, состояние нельзя было ни сохранить, ни
показать, а в списке вариантов лежали объекты AppEntry — то есть по протоколу
такое состояние не проехало бы вовсе.

Рина задаёт вопросы трёх видов, и все они устроены одинаково: спросили,
ждём ответа, через минуту вопрос протух.

    choose_app       какую из нескольких программ запустить
    confirm_action   подтвердить опасное системное действие
    confirm_command  подтвердить опасную пользовательскую команду

Поведение 3.1.0 воспроизводится буквально, включая неочевидное: **любая
нераспознанная реплика снимает вопрос** (см. docs/INVENTORY-3.1.0.md, §6).
Сказать «выключи компьютер», потом что-то постороннее, потом «да» — и ничего
не произойдёт. Для опасного действия это осторожная сторона ошибки, для
выбора программы — потерянный вопрос; менять это здесь нельзя, иначе
golden-набор покажет расхождение там, где его не задумывали.

Qt здесь нет: модуль лежит в ядре.
"""

import time
from dataclasses import dataclass, field, replace


#: Через сколько секунд заданный вопрос считается неактуальным.
TTL_SECONDS = 60

CHOOSE_APP = "choose_app"
CONFIRM_ACTION = "confirm_action"
CONFIRM_COMMAND = "confirm_command"

KINDS = (CHOOSE_APP, CONFIRM_ACTION, CONFIRM_COMMAND)


@dataclass(frozen=True)
class Question:
    """
    Заданный вопрос. Только сериализуемые значения.

    Варианты выбора хранятся словарями, а не объектами AppEntry: состояние
    обязано переживать запись в файл и дорогу по протоколу. Восстановить
    объект из словаря умеет сам индекс программ.
    """

    kind: str
    asked_at: float = field(default_factory=time.time)
    #: для confirm_action
    action: str = ""
    #: для confirm_command
    command_id: str = ""
    #: для choose_app — список словарей вида AppEntry.to_dict()
    options: tuple = ()
    #: что искали, когда возник вопрос
    query: str = ""
    #: выданное подтверждение для опасного действия (4.0-C05).
    #: Хранится в вопросе, потому что согласие человека относится к
    #: конкретному вызову, а не к тому, что вопрос когда-то задавали.
    confirmation_id: str = ""

    def __post_init__(self):
        if self.kind not in KINDS:
            raise ValueError(f"неизвестный вид вопроса: {self.kind!r}")
        object.__setattr__(self, "options", tuple(self.options))

    def expired(self, now=None):
        return (now or time.time()) - self.asked_at > TTL_SECONDS

    def entries(self):
        """Варианты выбора обратно объектами индекса."""
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
        """options — список AppEntry."""
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
    Незакрытый вопрос и переходы вокруг него.

    Переходов ровно три, и других быть не должно:

        ask      — задали вопрос
        answered — на него ответили, вопрос снят
        dropped  — вопрос снят, не получив ответа (протух или перебит)
    """

    def __init__(self, question=None):
        self._question = question

    # ---------- чтение ----------
    def current(self, now=None):
        """Действующий вопрос или None. Протухший снимается здесь же."""
        if self._question is None:
            return None
        if self._question.expired(now):
            self._question = None
            return None
        return self._question

    @property
    def pending(self):
        return self.current() is not None

    # ---------- переходы ----------
    def ask(self, question):
        self._question = question
        return question

    def answered(self):
        """Вопрос закрыт ответом."""
        self._question = None

    def dropped(self):
        """
        Вопрос снят, не получив ответа.

        Так ведёт себя 3.1.0 на любой нераспознанной реплике. Отдельный
        переход от `answered`, потому что это разные события: одно значит
        «поняли», другое — «забыли».
        """
        self._question = None

    # ---------- состояние ----------
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
