"""
Строка ввода команд — «командная строка ассистента».

Позволяет прогнать весь конвейер команд (плагины → пользовательские →
встроенные) вводом текста, без микрофона. Отправляет введённый текст в
VoiceService.process_command через сигнал.
"""

from PySide6.QtWidgets import QWidget, QHBoxLayout, QLineEdit, QPushButton
from PySide6.QtCore import Qt, Signal

from core.i18n import t as tr
from core.theme import Color, FONT_FAMILY, Radius


class CommandBar(QWidget):
    submitted = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._history = []
        self._hist_pos = 0
        self._build()

    def _build(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 12)
        layout.setSpacing(10)

        self.input = QLineEdit()
        self.input.setPlaceholderText(
            tr("Введите команду, напр. «запусти калькулятор» и нажмите Enter…"))
        self.input.setFixedHeight(40)
        self.input.returnPressed.connect(self._submit)
        layout.addWidget(self.input, 1)

        self.send_btn = QPushButton(tr("Отправить"))
        self.send_btn.setCursor(Qt.PointingHandCursor)
        self.send_btn.setFixedHeight(40)
        self.send_btn.clicked.connect(self._submit)
        layout.addWidget(self.send_btn)

        self.apply_theme()

    def apply_theme(self):
        self.input.setStyleSheet(f"""
            QLineEdit {{
                background: {Color.CRUST}; color: {Color.TEXT};
                border: 1px solid {Color.SURFACE_0}; border-radius: {Radius.MD}px;
                padding: 6px 16px; font-family: '{FONT_FAMILY}'; font-size: 13px;
            }}
            QLineEdit:focus {{ border: 1px solid {Color.ACCENT}; }}
        """)
        self.send_btn.setStyleSheet(f"""
            QPushButton {{
                background: {Color.ACCENT}; color: #ffffff;
                border: none; border-radius: {Radius.MD}px;
                padding: 6px 22px; font-size: 13px; font-weight: 600;
            }}
            QPushButton:hover {{ background: {Color.MAUVE}; }}
            QPushButton:pressed {{ background: {Color.SURFACE_2}; }}
        """)

    def _submit(self):
        text = self.input.text().strip()
        if not text:
            return
        self._history.append(text)
        self._hist_pos = len(self._history)
        self.input.clear()
        self.submitted.emit(text)

    def keyPressEvent(self, event):
        # стрелки вверх/вниз — история введённых команд
        if event.key() == Qt.Key_Up and self._history:
            self._hist_pos = max(0, self._hist_pos - 1)
            self.input.setText(self._history[self._hist_pos])
        elif event.key() == Qt.Key_Down and self._history:
            self._hist_pos = min(len(self._history), self._hist_pos + 1)
            if self._hist_pos == len(self._history):
                self.input.clear()
            else:
                self.input.setText(self._history[self._hist_pos])
        else:
            super().keyPressEvent(event)
