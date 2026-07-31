from PySide6.QtWidgets import QAbstractButton
from PySide6.QtCore import (
    Qt, Property, QPropertyAnimation, QEasingCurve, QSize, QRectF,
)
from PySide6.QtGui import QPainter, QColor

from core.theme import Color


class ToggleSwitch(QAbstractButton):
    """Анимированный переключатель (iOS-style)."""

    def __init__(self, checked=False, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(48, 26)

        self._offset = 1.0 if checked else 0.0
        self.toggled.connect(self._animate)

    def sizeHint(self):
        return QSize(48, 26)

    def get_offset(self):
        return self._offset

    def set_offset(self, v):
        self._offset = v
        self.update()

    offset = Property(float, get_offset, set_offset)

    def _animate(self, checked):
        anim = QPropertyAnimation(self, b"offset", self)
        anim.setDuration(260)
        anim.setStartValue(self._offset)
        anim.setEndValue(1.0 if checked else 0.0)
        # лёгкий «пружинистый» доводчик бегунка
        anim.setEasingCurve(QEasingCurve.OutBack)
        anim.start()
        self._anim = anim

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        t = max(0.0, min(1.0, self._offset))  # клампим (OutBack выходит за [0,1])

        # трек: плавный переход нейтраль → акцент
        p.setPen(Qt.NoPen)
        off_color = QColor(Color.SURFACE_1)
        on_color = QColor(Color.ACCENT)
        p.setBrush(QColor(
            int(off_color.red() + (on_color.red() - off_color.red()) * t),
            int(off_color.green() + (on_color.green() - off_color.green()) * t),
            int(off_color.blue() + (on_color.blue() - off_color.blue()) * t),
        ))
        p.drawRoundedRect(self.rect(), 13, 13)

        # бегунок
        d = self.height() - 6
        x = 3 + t * (self.width() - d - 6)
        p.setBrush(QColor("#ffffff"))
        p.drawEllipse(QRectF(x, 3, d, d))
        p.end()
