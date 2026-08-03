from plugins.api import Plugin
from plugins.settings_spec import Toggle, Text, Choice, Slider
from plugins.page_spec import Title, Note, Items, Button, Divider


class NotesPlugin(Plugin):
    """
    Демонстрация расширенного API: вкладка + настройки + команда.

    Вкладка описана декларативно (API v2) — плагин не импортирует Qt,
    поэтому его не придётся переписывать при смене оболочки приложения.
    """

    page_title = "Заметки"
    page_icon = "📝"

    def on_enable(self):
        self.log("Плагин заметок включён")

    # --- команда: «запиши купить молоко» ---
    def on_command(self, text):
        low = text.lower()
        if low.startswith("запиши") or "заметка" in low:
            note = text.split(" ", 1)[1] if " " in text else ""
            if note:
                notes = self.ctx.get_setting("items", []) or []
                notes.append(note)
                self.ctx.set_setting("items", notes[-self._limit():])
            self.respond(f"Записала: {note}" if note else "Что записать?")
            return True
        return False

    # --- декларативные настройки (панель строит приложение) ---
    def settings_schema(self):
        return [
            Toggle("announce", "Озвучивать при записи", default=True,
                   description="Проговаривать заметку вслух"),
            Choice("sort", "Сортировка", options=["новые сверху", "старые сверху"],
                   description="Порядок отображения"),
            Slider("limit", "Максимум заметок", min=5, max=100, default=20),
            Text("prefix", "Префикс заметки", default="•"),
        ]

    # --- своя вкладка (API v2: описание, а не виджеты) ---
    def page(self):
        notes = self._visible_notes()
        prefix = self.setting("prefix", "•")

        elements = [Title("Мои заметки")]
        if notes:
            elements.append(Note(f"Всего записей: {len(notes)}"))
            elements.append(Items(f"{prefix} {n}" for n in notes))
            elements.append(Divider())
            elements.append(Button("Очистить список", action="clear",
                                   variant="danger"))
        else:
            elements.append(
                Note("Пока пусто. Скажите: «запиши купить молоко»."))
        return elements

    def on_action(self, action, value=None):
        if action == "clear":
            self.ctx.set_setting("items", [])
            self.log("Список заметок очищен")

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
