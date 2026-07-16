from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QLabel,
    QPushButton,
)
from PySide6.QtCore import Qt, Signal

from core.theme import Color, FONT_FAMILY
from core.assets import logo_pixmap


class TitleBar(QWidget):

    close_clicked = Signal()
    minimize_clicked = Signal()
    maximize_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.old_pos = None

        self.setFixedHeight(46)
        self.setObjectName("titlebar")
        self.setup_ui()

    def setup_ui(self):
        self.setStyleSheet(f"""
            QWidget#titlebar {{
                background: transparent;
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 0, 10, 0)
        layout.setSpacing(0)

        self.title = QLabel("Rina Assistant")
        self.dot = QLabel()
        self.dot.setPixmap(logo_pixmap(22))
        self.dot.setFixedSize(22, 22)
        self.dot.setAlignment(Qt.AlignCenter)
        self.dot.setStyleSheet("margin-right: 8px;")

        layout.addWidget(self.dot)
        layout.addWidget(self.title)
        layout.addStretch()

        self.min_btn = self._make_button("–")
        self.max_btn = self._make_button("▢")
        self.close_btn = self._make_button("✕", danger=True)

        layout.addWidget(self.min_btn)
        layout.addSpacing(2)
        layout.addWidget(self.max_btn)
        layout.addSpacing(2)
        layout.addWidget(self.close_btn)

        self.min_btn.clicked.connect(self.minimize_clicked.emit)
        self.max_btn.clicked.connect(self.maximize_clicked.emit)
        self.close_btn.clicked.connect(self.close_clicked.emit)

        self.apply_theme()

    def _make_button(self, text, danger=False):
        btn = QPushButton(text)
        btn.setFixedSize(38, 30)
        btn.setCursor(Qt.PointingHandCursor)
        btn._danger = danger
        self._style_button(btn)
        return btn

    def _style_button(self, btn):
        hover_bg = Color.RED if btn._danger else Color.SURFACE_0
        hover_fg = "#ffffff" if btn._danger else Color.TEXT
        btn.setStyleSheet(f"""
            QPushButton {{
                color: {Color.SUBTEXT};
                background: transparent;
                border: none;
                font-size: 15px;
                border-radius: 8px;
            }}
            QPushButton:hover {{
                background: {hover_bg};
                color: {hover_fg};
            }}
            QPushButton:pressed {{
                background: {Color.SURFACE_1};
            }}
        """)

    def apply_theme(self):
        self.title.setStyleSheet(f"""
            color: {Color.TEXT};
            font-family: '{FONT_FAMILY}';
            font-size: 13px;
            font-weight: 600;
            letter-spacing: 0.3px;
        """)
        for btn in (self.min_btn, self.max_btn, self.close_btn):
            self._style_button(btn)

    # ---- перемещение окна ----
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.old_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        if self.old_pos and not self.parent_window.isMaximized():
            delta = event.globalPosition().toPoint() - self.old_pos
            self.parent_window.move(self.parent_window.pos() + delta)
            self.old_pos = event.globalPosition().toPoint()

    def mouseReleaseEvent(self, event):
        self.old_pos = None

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.maximize_clicked.emit()
