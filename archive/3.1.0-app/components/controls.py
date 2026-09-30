from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QSlider,
    QComboBox, QLineEdit
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from core.theme import Color, FONT_FAMILY, Radius


def styled_slider(minimum, maximum, value):
    s = QSlider(Qt.Horizontal)
    s.setMinimum(minimum)
    s.setMaximum(maximum)
    s.setValue(value)
    s.setCursor(Qt.PointingHandCursor)
    s.setStyleSheet(f"""
        QSlider::groove:horizontal {{
            height: 6px;
            background: {Color.SURFACE_0};
            border-radius: 3px;
        }}
        QSlider::sub-page:horizontal {{
            background: {Color.ACCENT};
            border-radius: 3px;
        }}
        QSlider::handle:horizontal {{
            background: #ffffff;
            width: 16px;
            height: 16px;
            margin: -5px 0;
            border-radius: 8px;
        }}
        QSlider::handle:horizontal:hover {{
            background: {Color.PINK};
        }}
    """)
    return s


def styled_combo(items, current=0):
    c = QComboBox()
    c.addItems(items)
    c.setCurrentIndex(current)
    c.setCursor(Qt.PointingHandCursor)
    c.setFixedHeight(38)
    c.setStyleSheet(f"""
        QComboBox {{
            background: {Color.SURFACE_0};
            color: {Color.TEXT};
            border: 1px solid {Color.SURFACE_1};
            border-radius: {Radius.SM}px;
            padding: 4px 14px;
            font-size: 13px;
            min-width: 180px;
        }}
        QComboBox:hover {{
            border: 1px solid {Color.ACCENT};
        }}
        QComboBox::drop-down {{
            border: none;
            width: 28px;
        }}
        QComboBox::down-arrow {{
            image: none;
            border-left: 5px solid transparent;
            border-right: 5px solid transparent;
            border-top: 6px solid {Color.SUBTEXT};
            margin-right: 10px;
        }}
        QComboBox QAbstractItemView {{
            background: {Color.CRUST};
            color: {Color.TEXT};
            border: 1px solid {Color.SURFACE_1};
            border-radius: {Radius.SM}px;
            selection-background-color: {Color.ACCENT};
            selection-color: #ffffff;
            outline: none;
            padding: 4px;
        }}
    """)
    return c


def styled_lineedit(placeholder="", text=""):
    e = QLineEdit()
    e.setPlaceholderText(placeholder)
    e.setText(text)
    e.setFixedHeight(38)
    e.setStyleSheet(f"""
        QLineEdit {{
            background: {Color.SURFACE_0};
            color: {Color.TEXT};
            border: 1px solid {Color.SURFACE_1};
            border-radius: {Radius.SM}px;
            padding: 4px 14px;
            font-size: 13px;
            min-width: 180px;
        }}
        QLineEdit:focus {{
            border: 1px solid {Color.ACCENT};
        }}
    """)
    return e


class SettingRow(QWidget):
    """
    Строка настройки: слева заголовок + подпись, справа — контрол
    (тумблер / слайдер / комбо / поле).

    Без иконки: эмодзи в каждой строке ничего не сообщали и превращали
    список настроек в пёстрый шум. Ориентироваться помогают заголовки секций.
    """

    def __init__(self, title, subtitle, control, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 8, 2, 8)
        layout.setSpacing(14)

        text_box = QVBoxLayout()
        text_box.setSpacing(2)
        t = QLabel(title)
        t.setFont(QFont(FONT_FAMILY, 12, QFont.Bold))
        t.setStyleSheet(f"color: {Color.TEXT};")
        s = QLabel(subtitle)
        s.setStyleSheet(f"color: {Color.OVERLAY}; font-size: 11px;")
        s.setWordWrap(True)
        text_box.addWidget(t)
        text_box.addWidget(s)
        layout.addLayout(text_box, 1)

        self.control = control
        layout.addWidget(control, 0, Qt.AlignVCenter)


class Divider(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(1)
        self.setStyleSheet(f"background: {Color.SURFACE_0};")
