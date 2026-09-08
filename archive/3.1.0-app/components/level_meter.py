from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, Property, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QPainter, QColor

from core.theme import Color, Radius


class LevelMeter(QWidget):
    """Горизонтальный индикатор уровня микрофона (0..1) с плавной анимацией."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(14)
        self.setMinimumWidth(160)
        self._level = 0.0

    def get_level(self):
        return self._level

    def set_level(self, v):
        self._level = max(0.0, min(1.0, v))
        self.update()

    level = Property(float, get_level, set_level)

    def animate_to(self, value, duration=180):
        anim = QPropertyAnimation(self, b"level", self)
        anim.setDuration(duration)
        anim.setStartValue(self._level)
        anim.setEndValue(max(0.0, min(1.0, value)))
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.start()
        self._anim = anim

    def reset(self):
        self.animate_to(0.0, 300)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        # дорожка
        p.setBrush(QColor(Color.SURFACE_0))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(self.rect(), 7, 7)

        # заполнение — цвет зависит от уровня (тихо→зелёный, громко→персик/красный)
        if self._level > 0:
            w = int(self.width() * self._level)
            if self._level < 0.55:
                color = QColor(Color.GREEN)
            elif self._level < 0.85:
                color = QColor(Color.PEACH)
            else:
                color = QColor(Color.RED)
            p.setBrush(color)
            p.drawRoundedRect(0, 0, max(7, w), self.height(), 7, 7)
        p.end()
