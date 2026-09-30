"""
Индикатор статуса — небольшая сплошная точка.

Статус меняется редко, поэтому индикатор статичный: постоянная пульсация
притягивает взгляд к тому, что не требует внимания. Анимация в интерфейсе
остаётся там, где она что-то сообщает (например, идёт запись микрофона).
"""

from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainter, QColor

from core.theme import Color


class StatusDot(QWidget):
    def __init__(self, color_attr="GREEN", diameter=8, parent=None):
        super().__init__(parent)
        self._color_attr = color_attr
        self._d = diameter
        self.setFixedSize(diameter + 4, diameter + 4)

    def _color(self):
        return QColor(getattr(Color, self._color_attr, Color.GREEN))

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        cx, cy = self.width() / 2, self.height() / 2
        r = self._d / 2
        p.setBrush(self._color())
        p.setPen(Qt.NoPen)
        p.drawEllipse(QRectF(cx - r, cy - r, self._d, self._d))
        p.end()
