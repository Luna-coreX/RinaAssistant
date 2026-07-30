"""
Плавающая строка команд — компактное окно поверх всех окон.

Показывается, когда основное окно свёрнуто (в панель задач или трей), если
включена настройка floating_command_bar. Позволяет вводить команды текстом,
когда микрофон недоступен/неудобен, и отправляет их в тот же конвейер команд.

Есть кнопка микрофона (разовое прослушивание) и крестик (спрятать строку на
текущую сессию). Окно перетаскивается за корпус.
"""

from PySide6.QtWidgets import QWidget, QHBoxLayout, QLineEdit, QPushButton, QLabel
from PySide6.QtCore import Qt, Signal, QPoint
from PySide6.QtGui import QPainter, QColor, QGuiApplication

from core.i18n import t as tr
from core.theme import Color, FONT_FAMILY, Radius
from core.assets import logo_pixmap


class FloatingCommandBar(QWidget):
    submitted = Signal(str)        # введённая команда
    mic_requested = Signal()       # нажата кнопка микрофона
    closed = Signal()              # строку закрыли крестиком

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._drag = None
        self._history = []
        self._hist_pos = 0
        self._build()

    def _build(self):
        self.setFixedHeight(52)
        self.setFixedWidth(380)

        root = QHBoxLayout(self)
        root.setContentsMargins(10, 6, 10, 6)
        root.setSpacing(8)

        self.handle = QLabel()
        self.handle.setPixmap(logo_pixmap(22))
        self.handle.setCursor(Qt.SizeAllCursor)
        self.handle.setFixedWidth(26)
        self.handle.setAlignment(Qt.AlignCenter)
        root.addWidget(self.handle)

        self.input = QLineEdit()
        self.input.setPlaceholderText(tr("Команда для Рины…  (Enter — выполнить)"))
        self.input.setFixedHeight(38)
        self.input.returnPressed.connect(self._submit)
        root.addWidget(self.input, 1)

        self.mic_btn = self._icon_button("🎤", tr("Голосовая команда"))
        self.mic_btn.clicked.connect(self.mic_requested.emit)
        root.addWidget(self.mic_btn)

        self.close_btn = self._icon_button("✕", tr("Скрыть строку"))
        self.close_btn.clicked.connect(self._on_close)
        root.addWidget(self.close_btn)

        self.apply_theme()

    def _icon_button(self, text, tip):
        b = QPushButton(text)
        b.setCursor(Qt.PointingHandCursor)
        b.setFixedSize(32, 32)
        b.setToolTip(tip)
        return b

    def apply_theme(self):
        self.input.setStyleSheet(f"""
            QLineEdit {{
                background: {Color.SURFACE_0}; color: {Color.TEXT};
                border: 1px solid {Color.SURFACE_1}; border-radius: {Radius.SM}px;
                padding: 4px 12px; font-family: '{FONT_FAMILY}'; font-size: 13px;
            }}
            QLineEdit:focus {{ border: 1px solid {Color.ACCENT}; }}
        """)
        self.mic_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {Color.ACCENT};
                border: none; border-radius: 8px; font-size: 15px;
            }}
            QPushButton:hover {{ background: {Color.SURFACE_1}; }}
        """)
        self.close_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {Color.SUBTEXT};
                border: none; border-radius: 8px; font-size: 13px;
            }}
            QPushButton:hover {{ background: {Color.RED}; color: #ffffff; }}
        """)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QColor(Color.CRUST))
        p.setPen(QColor(Color.SURFACE_1))
        p.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1),
                          Radius.LG, Radius.LG)
        p.setBrush(QColor(Color.ACCENT))
        p.setPen(Qt.NoPen)
        p.drawEllipse(QPoint(6, self.height() // 2), 3, 3)
        p.end()

    def _position_bottom(self):
        screen = QGuiApplication.primaryScreen().availableGeometry()
        x = screen.center().x() - self.width() // 2
        y = screen.bottom() - self.height() - 40
        self.move(x, y)

    def show_bar(self):
        self._position_bottom()
        self.show()
        self.raise_()
        self.input.setFocus()

    def hide_bar(self):
        self.hide()

    def _on_close(self):
        self.hide()
        self.closed.emit()

    def _submit(self):
        text = self.input.text().strip()
        if not text:
            return
        self._history.append(text)
        self._hist_pos = len(self._history)
        self.input.clear()
        self.submitted.emit(text)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self._on_close()
            return
        if event.key() == Qt.Key_Up and self._history:
            self._hist_pos = max(0, self._hist_pos - 1)
            self.input.setText(self._history[self._hist_pos])
        elif event.key() == Qt.Key_Down and self._history:
            self._hist_pos = min(len(self._history), self._hist_pos + 1)
            self.input.setText("" if self._hist_pos == len(self._history)
                               else self._history[self._hist_pos])
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        if self._drag is not None:
            delta = event.globalPosition().toPoint() - self._drag
            self.move(self.pos() + delta)
            self._drag = event.globalPosition().toPoint()

    def mouseReleaseEvent(self, event):
        self._drag = None
