from plugins.api import Plugin
from plugins.settings_spec import Toggle, Text, Choice, Slider


class NotesPlugin(Plugin):
    """Демонстрация расширенного API: вкладка + настройки + команда."""

    page_title = "Заметки"
    page_icon = "📝"

    def on_enable(self):
        self.log("Плагин заметок включён")

    # --- команда: «запиши купить молоко» ---
    def on_command(self, text):
        low = text.lower()
        if low.startswith("запиши") or "заметка" in low:
            note = text.split(" ", 1)[1] if " " in text else ""
            notes = self.ctx.get_setting("items", []) or []
            notes.append(note)
            self.ctx.set_setting("items", notes)
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

    # --- своя вкладка ---
    def create_page(self):
        from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
        from PySide6.QtGui import QFont
        w = QWidget()
        v = QVBoxLayout(w)
        v.setSpacing(8)
        title = QLabel("Мои заметки")
        title.setFont(QFont("Segoe UI", 14))
        v.addWidget(title)
        notes = self.ctx.get_setting("items", []) or []
        prefix = self.setting("prefix", "•")
        if not notes:
            v.addWidget(QLabel("Пока пусто. Скажите: «запиши купить молоко»."))
        for n in notes[-20:]:
            v.addWidget(QLabel(f"{prefix} {n}"))
        return w
