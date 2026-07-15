"""
Поле захвата горячей клавиши: кликаешь, жмёшь комбинацию — она записывается.

Показывает текущую комбинацию в Qt-нотации («Ctrl+Shift+R»). При фокусе
перехватывает нажатия и собирает модификаторы + основную клавишу.
"""

from PySide6.QtWidgets import QPushButton
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence

from core.i18n import t as tr
from core.theme import Color, FONT_FAMILY, Radius


class KeyCaptureEdit(QPushButton):
    """Кнопка-поле: клик → «Нажмите клавиши…» → ловит комбинацию."""

    captured = Signal(str)

    def __init__(self, sequence="", parent=None):
        super().__init__(parent)
        self._sequence = sequence
        self._capturing = False
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(38)
        self.setFocusPolicy(Qt.StrongFocus)
        self.clicked.connect(self._start_capture)
        self._update_text()
        self.apply_theme()

    def sequence(self):
        return self._sequence

    def set_sequence(self, seq):
        self._sequence = seq or ""
        self._update_text()

    def _update_text(self):
        if self._capturing:
            self.setText(tr("Нажмите клавиши…  (Esc — отмена)"))
        else:
            self.setText(self._sequence or tr("— не задано —"))

    def apply_theme(self):
        border = Color.ACCENT if self._capturing else Color.SURFACE_1
        self.setStyleSheet(f"""
            QPushButton {{
                background: {Color.SURFACE_0}; color: {Color.TEXT};
                border: 1px solid {border}; border-radius: {Radius.SM}px;
                padding: 4px 14px; font-family: '{FONT_FAMILY}'; font-size: 13px;
                text-align: left; min-width: 170px;
            }}
            QPushButton:hover {{ border: 1px solid {Color.ACCENT}; }}
        """)

    def _start_capture(self):
        self._capturing = True
        self._update_text()
        self.apply_theme()
        self.setFocus()

    def _stop_capture(self):
        self._capturing = False
        self._update_text()
        self.apply_theme()

    def keyPressEvent(self, event):
        if not self._capturing:
            return super().keyPressEvent(event)

        key = event.key()
        if key == Qt.Key_Escape:
            self._stop_capture()
            return

        # игнорируем одиночные модификаторы — ждём основную клавишу
        if key in (Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt, Qt.Key_Meta):
            return

        mods = event.modifiers()
        parts = []
        if mods & Qt.ControlModifier:
            parts.append("Ctrl")
        if mods & Qt.ShiftModifier:
            parts.append("Shift")
        if mods & Qt.AltModifier:
            parts.append("Alt")
        if mods & Qt.MetaModifier:
            parts.append("Meta")

        key_name = QKeySequence(key).toString()
        if not key_name:
            return
        parts.append(key_name)

        self._sequence = "+".join(parts)
        self._stop_capture()
        self.captured.emit(self._sequence)

    def focusOutEvent(self, event):
        if self._capturing:
            self._stop_capture()
        super().focusOutEvent(event)
