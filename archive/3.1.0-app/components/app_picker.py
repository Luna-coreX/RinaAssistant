"""
Поле выбора программы для конструктора команд.

Раньше здесь просили путь к .exe и кнопку «Обзор…». Теперь Рина знает, что
установлено на компьютере, поэтому достаточно начать печатать название —
остальное подставится. Ручной выбор файла остался для portable-программ,
которых нет в индексе.

Кроме пути хранится вид цели: у приложений Магазина вместо файла
AppUserModelID, и запускать его надо иначе.
"""

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QPushButton, QCompleter, QFileDialog
)
from PySide6.QtCore import Qt, Signal

from core.i18n import t as tr
from core.theme import Color, Radius
from components.controls import styled_lineedit


class AppPickerEdit(QWidget):
    """Поле с автодополнением по найденным программам + «Обзор…»."""

    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._target = ""
        self._kind = "file"
        self._by_name = {}

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        self.edit = styled_lineedit(tr("Начните вводить название программы"))
        self.edit.textChanged.connect(self._on_text_changed)
        row.addWidget(self.edit, 1)

        self.browse_btn = QPushButton(tr("Обзор…"))
        self.browse_btn.setCursor(Qt.PointingHandCursor)
        self.browse_btn.setFixedHeight(38)
        self.browse_btn.setStyleSheet(f"""
            QPushButton {{
                background: {Color.SURFACE_0}; color: {Color.TEXT};
                border: none; border-radius: {Radius.SM}px;
                padding: 4px 16px; font-size: 12px; font-weight: 600;
            }}
            QPushButton:hover {{ background: {Color.SURFACE_1}; }}
        """)
        self.browse_btn.clicked.connect(self._browse)
        row.addWidget(self.browse_btn)

        self._setup_completer()

    # ---------- автодополнение ----------
    def _setup_completer(self):
        try:
            from voice import app_index
            entries = app_index.cached_index()
        except Exception:
            entries = []

        self._by_name = {}
        for entry in entries:
            # при одинаковых именах побеждает более приоритетный источник —
            # он идёт раньше в отсортированном индексе
            self._by_name.setdefault(entry.name, entry)

        completer = QCompleter(list(self._by_name.keys()), self)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        completer.setMaxVisibleItems(12)
        completer.activated.connect(self._on_picked)
        self.edit.setCompleter(completer)

    def _on_picked(self, name):
        entry = self._by_name.get(name)
        if entry is not None:
            self._target, self._kind = entry.launch, entry.kind
            self.changed.emit()

    def _on_text_changed(self, text):
        text = text.strip()
        entry = self._by_name.get(text)
        if entry is not None:
            # выбрали known-программу — запоминаем, чем её запускать
            self._target, self._kind = entry.launch, entry.kind
        else:
            # это путь или просто имя команды («discord») — оставляем как есть
            self._target, self._kind = text, "file"
        self.changed.emit()

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, tr("Выберите программу"), "",
            tr("Программы (*.exe *.lnk *.bat *.cmd);;Все файлы (*)"))
        if path:
            self._target, self._kind = path, "file"
            self.edit.blockSignals(True)
            self.edit.setText(path)
            self.edit.blockSignals(False)
            self.changed.emit()

    # ---------- значения ----------
    def target(self):
        """Что запускать: путь к файлу или идентификатор приложения."""
        return self._target

    def target_kind(self):
        return self._kind

    def set_target(self, target, kind="file"):
        """Заполнить поле при редактировании существующей команды."""
        self._target = target or ""
        self._kind = kind or "file"
        # показываем понятное имя, если такая программа есть в индексе
        display = self._target
        for name, entry in self._by_name.items():
            if entry.launch == self._target:
                display = name
                break
        self.edit.blockSignals(True)
        self.edit.setText(display)
        self.edit.blockSignals(False)

    def setPlaceholderText(self, text):
        self.edit.setPlaceholderText(text)
