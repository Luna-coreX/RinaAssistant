"""
Пульсирующий индикатор статуса «онлайн».

Рисует яркую точку с мягким «дышащим» ореолом вокруг — живой акцент
в духе футуристичного интерфейса. Цвет по умолчанию — зелёный из темы.
"""

from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QRectF, QPropertyAnimation, QEasingCurve, Property
from PySide6.QtGui import QPainter, QColor, QRadialGradient

from core.theme import Color


class StatusDot(QWidget):
    def __init__(self, color_attr="GREEN", diameter=10, parent=None):
        super().__init__(parent)
        self._color_attr = color_attr
        self._d = diameter
        self._pulse = 0.0
        self.setFixedSize(diameter + 12, diameter + 12)

        self._anim = QPropertyAnimation(self, b"pulse", self)
        self._anim.setDuration(1700)
        self._anim.setStartValue(0.0)
        self._anim.setKeyValueAt(0.5, 1.0)
        self._anim.setEndValue(0.0)
        self._anim.setEasingCurve(QEasingCurve.InOutSine)
        self._anim.setLoopCount(-1)
        self._anim.start()

    def get_pulse(self):
        return self._pulse

    def set_pulse(self, v):
        self._pulse = v
        self.update()

    pulse = Property(float, get_pulse, set_pulse)

    def _color(self):
        return QColor(getattr(Color, self._color_attr, Color.GREEN))

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        cx, cy = self.width() / 2, self.height() / 2
        base = self._color()

        # дышащий ореол
        halo_r = (self._d / 2) + 3 + self._pulse * 3
        grad = QRadialGradient(cx, cy, halo_r)
        glow = QColor(base)
        glow.setAlphaF(0.35 * (1.0 - self._pulse) + 0.12)
        grad.setColorAt(0.0, glow)
        transparent = QColor(base)
        transparent.setAlphaF(0.0)
        grad.setColorAt(1.0, transparent)
        p.setBrush(grad)
        p.setPen(Qt.NoPen)
        p.drawEllipse(QRectF(cx - halo_r, cy - halo_r, halo_r * 2, halo_r * 2))

        # ядро
        p.setBrush(base)
        r = self._d / 2
        p.drawEllipse(QRectF(cx - r, cy - r, self._d, self._d))
        p.end()
