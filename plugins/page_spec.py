"""
Декларативное описание страницы плагина (схема версии 2).

Раньше плагин возвращал готовый QWidget. Это удобно ровно до тех пор, пока
интерфейс написан на Qt: такой плагин невозможно показать в другой оболочке
и нельзя отрисовать за пределами Python-процесса.

Поэтому плагин описывает страницу списком элементов, а рисует их оболочка:

    from plugins.api import Plugin
    from plugins.page_spec import Card, Title, Note, Items, Button, Row

    class NotesPlugin(Plugin):
        def page(self):
            notes = self.ctx.get_setting("items", []) or []
            return [
                Card([
                    Title("Мои заметки"),
                    Note(f"Всего: {len(notes)}"),
                    Items(notes) if notes else Note("Пока пусто"),
                ], title="Заметки"),
                Row([
                    Button("Очистить", action="clear", variant="danger"),
                    Button("Обновить", action="refresh"),
                ]),
            ]

        def on_action(self, action, value=None):
            if action == "clear":
                self.ctx.set_setting("items", [])

Элементы — обычные данные без зависимостей от Qt, поэтому такую страницу
нарисует любая оболочка, в том числе не на Python.

**Схема семантическая, а не визуальная.** Плагин говорит «предупреждение»,
а не «оранжевая рамка»; «карточка», а не «скруглить восемь пикселей». Ни
одного поля о внешности здесь нет и не будет: цвет, отступ и шрифт знает
тот, кто рисует. Именно поэтому версия 1 пережила редизайн почти целиком.

Полное описание — [PAGE-SCHEMA-v2](../docs/plugins/PAGE-SCHEMA-v2.md).
"""

from dataclasses import dataclass, field
from typing import List, Optional

#: Версия схемы. Растёт при несовместимом изменении словаря; добавление
#: элемента несовместимым не считается — незнакомый вид рендерер обязан
#: показать, а не пропустить.
SCHEMA_VERSION = 2

#: Докуда рендереру разрешено спускаться по вложенности.
#:
#: Ограничение не про красоту. Описание приходит из другого процесса, и
#: «сколько угодно вложенных карточек» — способ занять оболочку рисованием
#: вместо ответа человеку.
MAX_DEPTH = 4

#: Виды, у которых есть вложенное содержимое.
CONTAINERS = ("card", "group", "row")

#: Все виды словаря — для сверки со рендерером (`4.0-H02`).
KINDS = ("title", "text", "note", "items", "button", "input", "table",
         "progress", "badge", "divider") + CONTAINERS


@dataclass
class Element:
    kind: str
    text: str = ""
    items: Optional[List[str]] = None
    action: str = ""
    variant: str = "normal"      # для кнопок: normal | danger
    value: object = None
    children: List["Element"] = field(default_factory=list)

    def to_dict(self):
        """
        Сериализация: страница уходит в оболочку словарями.

        Пустые поля не пишутся — описание страницы ходит по проводу на
        каждое нажатие, и половина его иначе была бы пустыми строками.
        """
        data = {"kind": self.kind}
        if self.text:
            data["text"] = self.text
        if self.items:
            data["items"] = list(self.items)
        if self.action:
            data["action"] = self.action
        if self.variant != "normal":
            data["variant"] = self.variant
        if self.value is not None:
            data["value"] = self.value
        if self.children:
            data["children"] = [c.to_dict() for c in self.children
                                if isinstance(c, Element)]
        return data


# ---------------------------------------------------------------------------
# Листья
# ---------------------------------------------------------------------------
def Title(text):
    """Крупный заголовок раздела."""
    return Element(kind="title", text=str(text))


def Text(text):
    """Обычный текст."""
    return Element(kind="text", text=str(text))


def Note(text):
    """Мелкая пояснительная подпись."""
    return Element(kind="note", text=str(text))


def Items(items):
    """Список строк (заметки, задачи, результаты)."""
    return Element(kind="items", items=[str(i) for i in (items or [])])


def Button(label, action, variant="normal"):
    """Кнопка. При нажатии приложение вызовет plugin.on_action(action)."""
    return Element(kind="button", text=str(label), action=str(action),
                   variant=variant)


def Divider():
    """Разделительная линия."""
    return Element(kind="divider")


def Input(action, placeholder="", value="", button=""):
    """
    Поле ввода. При нажатии Enter (или кнопки рядом) приложение вызовет
    plugin.on_action(action, введённый_текст).
    """
    return Element(kind="input", action=str(action), text=str(placeholder),
                   value=str(value), variant=str(button or ""))


def Table(rows, headers=None):
    """
    Простая таблица: список строк, каждая — список ячеек.
    Заголовки необязательны.
    """
    return Element(kind="table",
                   items=[[str(c) for c in row] for row in (rows or [])],
                   value=[str(h) for h in headers] if headers else None)


def Progress(value, text=""):
    """Полоса прогресса: value от 0.0 до 1.0."""
    try:
        ratio = max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        ratio = 0.0
    return Element(kind="progress", value=ratio, text=str(text))


def Badge(text, variant="normal"):
    """Небольшая метка состояния: normal | good | warn | danger."""
    return Element(kind="badge", text=str(text), variant=variant)


# ---------------------------------------------------------------------------
# Контейнеры (схема версии 2, `4.0-H01`)
# ---------------------------------------------------------------------------
def _kids(children):
    """Только элементы: чужое в детях — молчаливая пустая карточка иначе."""
    return [c for c in (children or []) if isinstance(c, Element)]


def Card(children, title=""):
    """
    «Это одно целое.»

    Карточка отвечает на вопрос, что считать одной вещью: одна заметка,
    один прибор, один результат. Не «обведи рамкой» — рамка это решение
    оболочки, и в другом дизайне карточка может оказаться вовсе без рамки.
    """
    return Element(kind="card", text=str(title), children=_kids(children))


def Group(children, title=""):
    """
    «Это про одно.»

    Секция страницы: заголовок и то, что под ним. Отличается от карточки
    тем, что группирует **темы**, а не вещи, — так же, как секции экрана
    настроек отличаются от карточек в списке команд.
    """
    return Element(kind="group", text=str(title), children=_kids(children))


def Row(children):
    """
    «Это рядом друг с другом.»

    Просьба, а не приказ: на узком окне рендерер имеет право поставить
    содержимое столбиком. «Рядом» не выразимо на ширине в четыреста точек,
    и сжимать текст до двух букв хуже, чем нарушить просьбу.
    """
    return Element(kind="row", children=_kids(children))


def page_to_dict(elements):
    """Вся страница как список словарей (для передачи наружу)."""
    return [e.to_dict() for e in (elements or []) if isinstance(e, Element)]
