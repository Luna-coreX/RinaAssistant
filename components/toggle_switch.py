from PySide6.QtWidgets import QAbstractButton
from PySide6.QtCore import (
    Qt, Property, QPropertyAnimation, QEasingCurve, QSize, QRectF,
)
from PySide6.QtGui import QPainter, QColor, QLinearGradient

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

        # трек: выкл — нейтраль, вкл — неоновый градиент акцент→розовый
        p.setPen(Qt.NoPen)
        off_color = QColor(Color.SURFACE_1)
        if t <= 0.001:
            p.setBrush(off_color)
        else:
            grad = QLinearGradient(0, 0, self.width(), 0)
            a = QColor(Color.ACCENT)
            b = QColor(Color.ACCENT2)
            # подмешиваем нейтраль на промежуточных значениях
            def blend(c):
                return QColor(
                    int(off_color.red() + (c.red() - off_color.red()) * t),
                    int(off_color.green() + (c.green() - off_color.green()) * t),
                    int(off_color.blue() + (c.blue() - off_color.blue()) * t),
                )
            grad.setColorAt(0.0, blend(a))
            grad.setColorAt(1.0, blend(b))
            p.setBrush(grad)
        p.drawRoundedRect(self.rect(), 13, 13)

        # бегунок
        d = self.height() - 6
        x = 3 + t * (self.width() - d - 6)
        p.setBrush(QColor("#ffffff"))
        p.drawEllipse(QRectF(x, 3, d, d))
        p.end()
