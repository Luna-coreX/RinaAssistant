from PySide6.QtWidgets import QAbstractButton
from PySide6.QtCore import Qt, Property, QPropertyAnimation, QEasingCurve, QSize
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
        anim.setDuration(200)
        anim.setStartValue(self._offset)
        anim.setEndValue(1.0 if checked else 0.0)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.start()
        self._anim = anim

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        # трек
        off_color = QColor(Color.SURFACE_1)
        on_color = QColor(Color.ACCENT)
        track = QColor(
            int(off_color.red() + (on_color.red() - off_color.red()) * self._offset),
            int(off_color.green() + (on_color.green() - off_color.green()) * self._offset),
            int(off_color.blue() + (on_color.blue() - off_color.blue()) * self._offset),
        )
        p.setBrush(track)
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(self.rect(), 13, 13)

        # бегунок
        d = self.height() - 6
        x = 3 + self._offset * (self.width() - d - 6)
        p.setBrush(QColor("#ffffff"))
        p.drawEllipse(int(x), 3, d, d)
        p.end()
