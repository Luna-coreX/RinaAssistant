from PySide6.QtWidgets import QPushButton
from PySide6.QtCore import Qt, Property, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QColor, QPainter, QFont

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
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.start()
        self._active_anim = anim

    # ---------- отрисовка ----------
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        rect = self.rect().adjusted(2, 3, -2, -3)

        # фон
        if self._bg_alpha > 0:
            if self.isChecked():
                base = QColor(Color.ACCENT)
                base.setAlphaF(0.16 * self._bg_alpha + 0.0)
                bg = QColor(Color.ACCENT)
                bg.setAlphaF(0.15 * self._bg_alpha)
            else:
                bg = QColor(Color.SURFACE_0)
                bg.setAlphaF(self._bg_alpha)
            p.setBrush(bg)
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(rect, Radius.SM, Radius.SM)

        # индикатор слева
        if self._indicator > 0:
            h = rect.height() * 0.55 * self._indicator
            y = rect.center().y() - h / 2
            p.setBrush(QColor(Color.ACCENT))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(rect.left(), int(y), 4, int(h), 2, 2)

        # текст
        color = QColor(Color.TEXT if self.isChecked() else Color.SUBTEXT)
        p.setPen(color)
        f = self.font()
        f.setBold(self.isChecked())
        p.setFont(f)
        text_rect = rect.adjusted(14, 0, 0, 0)
        p.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, self.text())
        p.end()
