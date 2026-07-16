"""
Текстовая надпись с неоновой градиентной заливкой (акцент→розовый→синий).

Используется для брендового вордмарка «RINA». Перекрашивается вслед за
темой — цвета читаются из :data:`Color` на каждой отрисовке.
"""

from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import (
    QPainter, QFont, QFontMetrics, QLinearGradient, QColor, QPen,
)

from core.theme import Color, FONT_FAMILY


class GradientText(QWidget):
    def __init__(self, text, size=20, bold=True, tri=True,
                 letter_spacing=1.5, parent=None):
        super().__init__(parent)
        self._text = text
        self._tri = tri
        self._font = QFont(FONT_FAMILY, size, QFont.Bold if bold else QFont.Normal)
        self._font.setLetterSpacing(QFont.AbsoluteSpacing, letter_spacing)
        self._recalc()

    def setText(self, text):
        self._text = text
        self._recalc()
        self.update()

    def _recalc(self):
        fm = QFontMetrics(self._font)
        self._w = fm.horizontalAdvance(self._text)
        self._h = fm.height()
        self.setMinimumSize(self._w + 2, self._h + 2)

    def sizeHint(self):
        return QSize(self._w + 2, self._h + 2)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        p.setFont(self._font)

        grad = QLinearGradient(0, 0, self.width(), 0)
        if self._tri:
            grad.setColorAt(0.0, QColor(Color.ACCENT))
            grad.setColorAt(0.55, QColor(Color.ACCENT2))
            grad.setColorAt(1.0, QColor(Color.ACCENT3))
        else:
            grad.setColorAt(0.0, QColor(Color.ACCENT))
            grad.setColorAt(1.0, QColor(Color.ACCENT2))

        pen = QPen()
        pen.setBrush(grad)
        p.setPen(pen)
        p.drawText(self.rect(), Qt.AlignLeft | Qt.AlignVCenter, self._text)
        p.end()
