"""
Декларативное описание вкладки плагина (API v2).

Раньше плагин возвращал готовый QWidget. Это удобно ровно до тех пор, пока
интерфейс написан на Qt: такой плагин невозможно показать в другой оболочке
и нельзя отрисовать за пределами Python-процесса.

Поэтому плагин описывает вкладку списком элементов, а рисует их приложение:

    from plugins.api import Plugin
    from plugins.page_spec import Title, Text, Note, Items, Button, Divider

    class NotesPlugin(Plugin):
        def page(self):
            notes = self.ctx.get_setting("items", []) or []
            return [
                Title("Мои заметки"),
                Note(f"Всего: {len(notes)}"),
                Items(notes) if notes else Note("Пока пусто"),
                Divider(),
                Button("Очистить", action="clear", variant="danger"),
            ]

        def on_action(self, action, value=None):
            if action == "clear":
                self.ctx.set_setting("items", [])

Элементы — обычные данные без зависимостей от Qt, поэтому такую вкладку
сможет отрисовать любая оболочка (в том числе не на Python).
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Element:
    kind: str
    text: str = ""
    items: Optional[List[str]] = None
    action: str = ""
    variant: str = "normal"      # для кнопок: normal | danger
    value: object = None

    def to_dict(self):
        """Сериализация — понадобится, когда оболочка будет вне Python."""
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
        return data


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


def page_to_dict(elements):
    """Вся страница как список словарей (для передачи наружу)."""
    return [e.to_dict() for e in (elements or []) if isinstance(e, Element)]
