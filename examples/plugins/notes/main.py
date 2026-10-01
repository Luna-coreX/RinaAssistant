"""
Notes.

An example of a **page on the version 2 schema**: a card, a section, a row
of buttons and an input field. Before version 2 the dictionary was flat, and
there was nothing to express such a page with — only a column of paragraphs.
"""
from core.tools import Param
from plugins.api import Plugin, PluginTool
from plugins.page_spec import (Badge, Button, Card, Group, Input, Items, Note,
                               Row, Title)
from plugins.settings_spec import Choice, Slider, Text, Toggle


class NotesPlugin(Plugin):
    """
    A demonstration of the extended API: a page, settings, a command, a
    tool.

    The page is described declaratively — the plugin imports neither Qt nor
    WPF, so it did not have to be rewritten when the shell changed.
    """

    page_title = "Заметки"
    page_icon = "📝"

    def on_enable(self):
        self.log("Плагин заметок включён")

    # --- the declared tool ---
    def tools(self):
        return [
            PluginTool(
                name="add",
                summary="Записать заметку.",
                params=(Param("text", "string", "Что записать."),),
                run=lambda args: self._add(str(args.get("text", ""))),
            ),
        ]

    # --- a command: "запиши купить молоко" ---
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

    # --- declarative settings (the shell builds the panel) ---
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

    # --- a page of its own (the version 2 schema) ---
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

    # --- helpers ---
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
