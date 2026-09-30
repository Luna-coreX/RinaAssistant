from PySide6.QtWidgets import QFrame, QVBoxLayout
from PySide6.QtGui import QColor, QPainter, QPainterPath, QBrush, QPen
from PySide6.QtCore import Qt, QRectF
from core.theme import Color, Radius


class Card(QFrame):
    """
    Плоская карточка: сплошная поверхность и тонкая рамка.

    Отрисовка ручная (а не QGraphicsDropShadowEffect) — графический эффект
    на карточке конфликтует с opacity-эффектом родительской страницы во время
    анимации перехода, из-за чего карточки исчезали.

    SHADOW сохранён как поле отступа: карточки лежат встык в вертикальных
    списках, и небольшой внешний зазор отделяет их друг от друга.
    """

    SHADOW = 6  # внешний отступ (раньше — зона под многослойную тень)

    def __init__(self, parent=None, radius=Radius.LG):
        super().__init__(parent)
        self._radius = radius
        self.setObjectName("card")
        # прозрачный фон виджета — рисуем всё сами
        self.setStyleSheet("QFrame#card { background: transparent; }")
        self.setAttribute(Qt.WA_StyledBackground, True)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(
            20 + self.SHADOW, 18 + self.SHADOW,
            20 + self.SHADOW, 18 + self.SHADOW
        )
        self._layout.setSpacing(12)

    def layout(self):
        return self._layout

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        rect = QRectF(self.rect().adjusted(
            self.SHADOW, self.SHADOW, -self.SHADOW, -self.SHADOW
        )).adjusted(0.5, 0.5, -0.5, -0.5)

        path = QPainterPath()
        path.addRoundedRect(rect, self._radius, self._radius)
        p.fillPath(path, QBrush(QColor(Color.CRUST)))

        p.setPen(QPen(QColor(Color.SURFACE_0), 1))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
        p.end()
