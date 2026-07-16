from PySide6.QtWidgets import QPushButton
from PySide6.QtCore import Qt, Property, QPropertyAnimation, QEasingCurve, QRectF
from PySide6.QtGui import QColor, QPainter, QFont, QLinearGradient

from core.theme import Color, FONT_FAMILY, Radius


class NavButton(QPushButton):
    """
    Кнопка навигации с плавной подсветкой фона и
    вертикальным индикатором активной страницы слева.
    """

    def __init__(self, text, icon="", parent=None):
        super().__init__(parent)
        self._label = text
        self._icon = icon
        self.setText(f"  {icon}   {text}")
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(44)

        self._bg_alpha = 0.0        # 0..1 — насыщенность фона hover/active
        self._indicator = 0.0       # 0..1 — высота индикатора слева

        self.setFont(QFont(FONT_FAMILY, 11))
        self.setStyleSheet("QPushButton { border: none; background: transparent; }")

        self.toggled.connect(self._on_toggle)

    # ---------- анимируемые свойства ----------
    def get_bg(self):
        return self._bg_alpha

    def set_bg(self, v):
        self._bg_alpha = v
        self.update()

    bg = Property(float, get_bg, set_bg)

    def get_ind(self):
        return self._indicator

    def set_ind(self, v):
        self._indicator = v
        self.update()

    indicator = Property(float, get_ind, set_ind)

    # ---------- поведение ----------
    def _on_toggle(self, checked):
        self._animate(self, b"indicator", self._indicator,
                      1.0 if checked else 0.0, 220)
        self._animate(self, b"bg", self._bg_alpha,
                      1.0 if checked else 0.0, 220)

    def enterEvent(self, e):
        if not self.isChecked():
            self._animate(self, b"bg", self._bg_alpha, 0.45, 160)
        super().enterEvent(e)

    def leaveEvent(self, e):
        if not self.isChecked():
            self._animate(self, b"bg", self._bg_alpha, 0.0, 160)
        super().leaveEvent(e)

    def _animate(self, target, prop, start, end, dur):
        anim = QPropertyAnimation(target, prop, self)
        anim.setDuration(dur)
        anim.setStartValue(start)
        anim.setEndValue(end)
        anim.setEasingCurve(QEasingCurve.OutExpo)
        anim.start()
        self._active_anim = anim

    # ---------- отрисовка ----------
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        rect = QRectF(self.rect().adjusted(2, 3, -2, -3))

        # фон
        if self._bg_alpha > 0:
            if self.isChecked():
                # неоновая градиентная заливка активной вкладки
                grad = QLinearGradient(rect.left(), 0, rect.right(), 0)
                c1 = QColor(Color.ACCENT);  c1.setAlphaF(0.22 * self._bg_alpha)
                c2 = QColor(Color.ACCENT2); c2.setAlphaF(0.12 * self._bg_alpha)
                grad.setColorAt(0.0, c1)
                grad.setColorAt(1.0, c2)
                p.setBrush(grad)
                p.setPen(Qt.NoPen)
                p.drawRoundedRect(rect, Radius.SM, Radius.SM)
                # тонкая акцентная окантовка
                border = QColor(Color.ACCENT)
                border.setAlphaF(0.35 * self._bg_alpha)
                p.setBrush(Qt.NoBrush)
                p.setPen(border)
                p.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5),
                                  Radius.SM, Radius.SM)
            else:
                bg = QColor(Color.SURFACE_0)
                bg.setAlphaF(self._bg_alpha)
                p.setBrush(bg)
                p.setPen(Qt.NoPen)
                p.drawRoundedRect(rect, Radius.SM, Radius.SM)

        # индикатор слева со свечением
        if self._indicator > 0:
            h = rect.height() * 0.6 * self._indicator
            y = rect.center().y() - h / 2
            # мягкое свечение под индикатором
            glow = QColor(Color.ACCENT)
            glow.setAlphaF(0.30 * self._indicator)
            p.setBrush(glow)
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(QRectF(rect.left() - 1, y - 3, 8, h + 6), 5, 5)
            # сам индикатор — вертикальный градиент акцент→розовый
            ind = QLinearGradient(0, y, 0, y + h)
            ind.setColorAt(0.0, QColor(Color.ACCENT))
            ind.setColorAt(1.0, QColor(Color.ACCENT2))
            p.setBrush(ind)
            p.drawRoundedRect(QRectF(rect.left(), y, 4, h), 2, 2)

        # текст
        color = QColor(Color.TEXT if self.isChecked() else Color.SUBTEXT)
        p.setPen(color)
        f = self.font()
        f.setBold(self.isChecked())
        p.setFont(f)
        text_rect = self.rect().adjusted(16, 0, 0, 0)
        p.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, self.text())
        p.end()
