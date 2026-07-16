"""
Редактор последовательности шагов для конструктора команд.

Каждый шаг — упрощённая под-команда (без фраз активации): тип + цель.
Поддерживаемые типы шага: программа, папка, сайт, озвучить текст,
системное действие. Шаги выполняются по порядку.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QFileDialog
)
from PySide6.QtCore import Qt

from core.i18n import t as tr
from core.theme import Color, FONT_FAMILY, Radius
from components.controls import styled_combo, styled_lineedit
from voice.user_commands import SYSTEM_ACTIONS, make_command


# типы, доступные внутри последовательности (без вложенных последовательностей)
STEP_TYPES = [
    ("app",     "Программа",         "🖥️"),
    ("folder",  "Папка",             "📁"),
    ("website", "Сайт",              "🌐"),
    ("speak",   "Озвучить",          "🔊"),
    ("system",  "Системное действие","⚙️"),
]
_STEP_IDS = [t for t, _, _ in STEP_TYPES]


class StepRow(QWidget):
    """Одна строка шага последовательности."""

    def __init__(self, on_delete, step=None, parent=None):
        super().__init__(parent)
        self._on_delete = on_delete
        self._build()
        if step:
            self._load(step)
        self._sync_fields()

    def _build(self):
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 4, 0, 4)
        row.setSpacing(8)

        # номер/маркер
        self.handle = QLabel("≡")
        self.handle.setStyleSheet(f"color: {Color.OVERLAY}; font-size: 16px;")
        self.handle.setFixedWidth(16)
        row.addWidget(self.handle)

        # тип шага
        self.type_combo = styled_combo(
            [f"{icon} {tr(label)}" for _, label, icon in STEP_TYPES], 0)
        self.type_combo.setFixedWidth(150)
        self.type_combo.currentIndexChanged.connect(self._sync_fields)
        row.addWidget(self.type_combo)

        # цель: поле ввода (путь/url/текст)
        self.target_edit = styled_lineedit("")
        row.addWidget(self.target_edit, 1)

        # системное действие (альтернатива полю ввода)
        self.system_combo = styled_combo(
            [tr(label) for _, label in SYSTEM_ACTIONS], 0)
        self.system_combo.hide()
        row.addWidget(self.system_combo, 1)

        # обзор (для программы/папки)
        self.browse_btn = QPushButton("…")
        self.browse_btn.setFixedSize(34, 38)
        self.browse_btn.setCursor(Qt.PointingHandCursor)
        self.browse_btn.setStyleSheet(f"""
            QPushButton {{
                background: {Color.SURFACE_0}; color: {Color.TEXT};
                border: none; border-radius: {Radius.SM}px; font-size: 15px;
            }}
            QPushButton:hover {{ background: {Color.SURFACE_1}; }}
        """)
        self.browse_btn.clicked.connect(self._browse)
        row.addWidget(self.browse_btn)

        # удалить шаг
        self.del_btn = QPushButton("✕")
        self.del_btn.setFixedSize(34, 38)
        self.del_btn.setCursor(Qt.PointingHandCursor)
        self.del_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {Color.RED};
                border: 1px solid {Color.alpha(Color.RED, '55')}; border-radius: {Radius.SM}px;
                font-size: 13px;
            }}
            QPushButton:hover {{ background: {Color.alpha(Color.RED, '22')}; }}
        """)
        self.del_btn.clicked.connect(lambda: self._on_delete(self))
        row.addWidget(self.del_btn)

    def _current_type(self):
        idx = self.type_combo.currentIndex()
        return _STEP_IDS[idx] if 0 <= idx < len(_STEP_IDS) else "app"

    def _sync_fields(self, *args):
        t = self._current_type()
        is_system = (t == "system")
        is_pathlike = t in ("app", "folder")

        self.system_combo.setVisible(is_system)
        self.target_edit.setVisible(not is_system)
        self.browse_btn.setVisible(is_pathlike)

        placeholders = {
            "app": "Путь к программе или имя",
            "folder": "Путь к папке",
            "website": "example.com",
            "speak": "Текст для озвучивания",
        }
        if not is_system:
            self.target_edit.setPlaceholderText(placeholders.get(t, ""))

    def _browse(self):
        t = self._current_type()
        if t == "folder":
            path = QFileDialog.getExistingDirectory(self, tr("Выберите папку"))
        else:
            path, _ = QFileDialog.getOpenFileName(self, tr("Выберите программу"))
        if path:
            self.target_edit.setText(path)

    def _load(self, step):
        t = step.get("type", "app")
        if t in _STEP_IDS:
            self.type_combo.setCurrentIndex(_STEP_IDS.index(t))
        if t == "system":
            actions = [a for a, _ in SYSTEM_ACTIONS]
            if step.get("target") in actions:
                self.system_combo.setCurrentIndex(actions.index(step["target"]))
        else:
            self.target_edit.setText(step.get("target", ""))

    def to_step(self):
        """Возвращает под-команду или None, если шаг пустой/некорректный."""
        t = self._current_type()
        if t == "system":
            target = SYSTEM_ACTIONS[self.system_combo.currentIndex()][0]
        else:
            target = self.target_edit.text().strip()
            if not target:
                return None
        # у шагов нет фраз активации — они выполняются в составе последовательности
        return make_command(cmd_type=t, triggers=["_step"], target=target)


class SequenceEditor(QWidget):
    """Список шагов + кнопка добавления."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows = []
        self._build()

    def _build(self):
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(4)

        hint = QLabel(tr("Шаги выполняются по порядку сверху вниз:"))
        hint.setStyleSheet(f"color: {Color.OVERLAY}; font-size: 11px;")
        self._layout.addWidget(hint)

        self._rows_holder = QVBoxLayout()
        self._rows_holder.setSpacing(2)
        self._layout.addLayout(self._rows_holder)

        add = QPushButton(tr("＋ Добавить шаг"))
        add.setCursor(Qt.PointingHandCursor)
        add.setFixedHeight(34)
        add.setStyleSheet(f"""
            QPushButton {{
                background: {Color.SURFACE_0}; color: {Color.TEXT};
                border: 1px dashed {Color.SURFACE_2}; border-radius: {Radius.SM}px;
                font-size: 12px; font-weight: 600;
            }}
            QPushButton:hover {{ background: {Color.SURFACE_1}; }}
        """)
        add.clicked.connect(lambda: self.add_step())
        self._layout.addWidget(add)

    def add_step(self, step=None):
        row = StepRow(self._delete_row, step=step)
        self._rows.append(row)
        self._rows_holder.addWidget(row)

    def _delete_row(self, row):
        if row in self._rows:
            self._rows.remove(row)
            row.setParent(None)
            row.deleteLater()

    def load_steps(self, steps):
        # очистить и заполнить
        for row in list(self._rows):
            self._delete_row(row)
        for s in steps or []:
            self.add_step(s)

    def to_steps(self):
        steps = []
        for row in self._rows:
            s = row.to_step()
            if s is not None:
                steps.append(s)
        return steps
