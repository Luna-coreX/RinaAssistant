"""
Заметки.

Пример **страницы на схеме версии 2**: карточка, секция, ряд кнопок и
поле ввода. До версии 2 словарь был плоским, и такую страницу выразить
было нечем — только столбиком абзацев.
"""
from core.tools import Param
from plugins.api import Plugin, PluginTool
from plugins.page_spec import (Badge, Button, Card, Group, Input, Items, Note,
                               Row, Title)
from plugins.settings_spec import Choice, Slider, Text, Toggle


class NotesPlugin(Plugin):
    """
    Демонстрация расширенного API: страница, настройки, команда, инструмент.

    Страница описана декларативно — плагин не импортирует ни Qt, ни WPF,
    поэтому его не пришлось переписывать при смене оболочки.
    """

    page_title = "Заметки"
    page_icon = "📝"

    def on_enable(self):
        self.log("Плагин заметок включён")

    # --- объявленный инструмент ---
    def tools(self):
        return [
            PluginTool(
                name="add",
                summary="Записать заметку.",
                params=(Param("text", "string", "Что записать."),),
                run=lambda args: self._add(str(args.get("text", ""))),
            ),
        ]

    # --- команда: «запиши купить молоко» ---
    def on_command(self, text):
        low = text.lower()
        if low.startswith("запиши") or "заметка" in low:
            note = text.split(" ", 1)[1] if " " in text else ""
            self.respond(self._add(note) if note else "Что записать?")
            return True
        return False

    def _add(self, note):
        if not note.strip():
            return "Что записать?"
        notes = list(self.ctx.get_setting("items", []) or [])
        notes.append(note.strip())
        self.ctx.set_setting("items", notes[-self._limit():])
        return f"Записала: {note.strip()}"

    # --- декларативные настройки (панель строит оболочка) ---
    def settings_schema(self):
        return [
            Toggle("announce", "Озвучивать при записи", default=True,
                   description="Проговаривать заметку вслух"),
            Choice("sort", "Сортировка",
                   options=["новые сверху", "старые сверху"],
                   description="Порядок отображения"),
            Slider("limit", "Максимум заметок", min=5, max=100, default=20),
            Text("prefix", "Префикс заметки", default="•"),
        ]

    # --- своя страница (схема версии 2) ---
    def page(self):
        notes = self._visible_notes()
        prefix = self.setting("prefix", "•")

        if not notes:
            return [
                Card([
                    Title("Мои заметки"),
                    Note("Пока пусто. Скажите: «запиши купить молоко»."),
                    Input("add", placeholder="Или напишите здесь",
                          button="Записать"),
                ]),
            ]

        return [
            Card([
                Row([
                    Title("Мои заметки"),
                    Badge(f"{len(notes)}", variant="good"),
                ]),
                Items(f"{prefix} {n}" for n in notes),
                Input("add", placeholder="Ещё одна заметка",
                      button="Записать"),
            ]),
            Group([
                Row([
                    Button("Очистить список", action="clear",
                           variant="danger"),
                ]),
            ], title="Управление"),
        ]

    def on_action(self, action, value=None):
        if action == "clear":
            self.ctx.set_setting("items", [])
            self.log("Список заметок очищен")
        elif action == "add" and value:
            self._add(str(value))

    # --- вспомогательное ---
    def _limit(self):
        try:
            return max(1, int(self.setting("limit", 20)))
        except (TypeError, ValueError):
            return 20

    def _visible_notes(self):
        notes = list(self.ctx.get_setting("items", []) or [])
        notes = notes[-self._limit():]
        if self.setting("sort", "новые сверху") == "новые сверху":
            notes.reverse()
        return notes
