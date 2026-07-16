from PySide6.QtWidgets import QFrame, QVBoxLayout
from PySide6.QtGui import (
    QColor, QPainter, QPainterPath, QBrush, QPen, QLinearGradient,
)
from PySide6.QtCore import Qt, QRectF
from core.theme import Color, Radius


class Card(QFrame):
    """
    Карточка со скруглением и мягкой тенью.

    Тень рисуется вручную в paintEvent, а НЕ через
    QGraphicsDropShadowEffect. Это принципиально: графический
    эффект на карточке конфликтует с opacity-эффектом на
    родительской странице во время анимации перехода, из-за
    чего карточки исчезали. Нарисованная тень такого эффекта
    не имеет и переживает любые анимации родителя.
    """

    SHADOW = 16  # запас по краям под тень

    def __init__(self, parent=None, radius=Radius.LG):
        super().__init__(parent)
        self._radius = radius
        self.setObjectName("card")
        # прозрачный фон виджета — рисуем всё сами
        self.setStyleSheet("QFrame#card { background: transparent; }")
        self.setAttribute(Qt.WA_StyledBackground, True)

        self._layout = QVBoxLayout(self)
        # внутренние отступы + компенсация зоны тени
        self._layout.setContentsMargins(
            22 + self.SHADOW, 20 + self.SHADOW,
            22 + self.SHADOW, 20 + self.SHADOW
        )
        self._layout.setSpacing(12)

    def layout(self):
        return self._layout

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        rect = self.rect().adjusted(
            self.SHADOW, self.SHADOW, -self.SHADOW, -self.SHADOW
        )

        # мягкая тень: несколько полупрозрачных слоёв
        for i in range(self.SHADOW, 0, -2):
            alpha = int(6 * (1 - i / self.SHADOW))
            if alpha <= 0:
                continue
            p.setBrush(QColor(0, 0, 0, alpha))
            p.setPen(Qt.NoPen)
            shadow_rect = rect.adjusted(-i, -i + 3, i, i + 3)
            p.drawRoundedRect(shadow_rect, self._radius + i, self._radius + i)

        # тело карточки — лёгкий вертикальный градиент (стеклянный эффект)
        body = QLinearGradient(rect.left(), rect.top(),
                               rect.left(), rect.bottom())
        top = QColor(Color.SURFACE_0)
        top_c = QColor(Color.CRUST)
        # чуть подсветить верх для объёма
        body.setColorAt(0.0, QColor(
            min(255, top_c.red() + 6),
            min(255, top_c.green() + 6),
            min(255, top_c.blue() + 8)))
        body.setColorAt(1.0, top_c)
        path = QPainterPath()
        path.addRoundedRect(rect, self._radius, self._radius)
        p.fillPath(path, QBrush(body))

        # тонкая градиентная рамка: сверху акцентный отблеск, ниже — нейтраль
        border = QLinearGradient(rect.left(), rect.top(),
                                 rect.right(), rect.bottom())
        hi = QColor(Color.ACCENT); hi.setAlphaF(0.28)
        lo = QColor(Color.SURFACE_0)
        border.setColorAt(0.0, hi)
        border.setColorAt(0.35, lo)
        border.setColorAt(1.0, lo)
        p.setPen(QPen(QBrush(border), 1))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
        p.end()
