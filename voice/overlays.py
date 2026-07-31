"""
Всплывающие окна голосового интерфейса:
  - ListeningOverlay — окно «Слушаю…» с пульсирующим индикатором (по хоткею)
  - Toast            — уведомление с текстом ответа ассистента
  - MicWidget        — мини-виджет микрофона для режима «всегда слушать»

Все они — независимые frameless-окна поверх приложения (Qt.Tool),
чтобы показываться даже когда основное окно свёрнуто в трей.
"""

from PySide6.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout, QGraphicsOpacityEffect
)
from PySide6.QtCore import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve, Property, QPoint,
    QAbstractAnimation, Signal
)
from PySide6.QtGui import QPainter, QColor, QGuiApplication

from core.i18n import t as tr
from core.theme import Color, FONT_FAMILY, Radius
from core.assets import logo_pixmap


# ---------------------------------------------------------------------------
class ListeningOverlay(QWidget):
    """Окно «Слушаю…» с пульсирующим кругом."""

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(260, 160)

        self._pulse = 0.0
        self._pulse_anim = QPropertyAnimation(self, b"pulse", self)
        self._pulse_anim.setDuration(900)
        self._pulse_anim.setStartValue(0.0)
        self._pulse_anim.setEndValue(1.0)
        self._pulse_anim.setEasingCurve(QEasingCurve.InOutSine)
        self._pulse_anim.setLoopCount(-1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 90)
        layout.addStretch()
        self.label = QLabel(tr("Слушаю…"))
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setStyleSheet(
            f"color: {Color.TEXT}; font-family: '{FONT_FAMILY}'; "
            f"font-size: 15px; font-weight: 600;")
        layout.addWidget(self.label)

    def get_pulse(self):
        return self._pulse

    def set_pulse(self, v):
        self._pulse = v
        self.update()

    pulse = Property(float, get_pulse, set_pulse)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        # фон-карточка
        p.setBrush(QColor(Color.CRUST))
        p.setPen(QColor(Color.SURFACE_1))
        p.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1),
                          Radius.LG, Radius.LG)

        # пульсирующие круги
        cx, cy = self.width() / 2, 62
        accent = QColor(Color.ACCENT)
        for i, base_r in enumerate((34, 26, 18)):
            r = base_r + self._pulse * (8 - i * 2)
            a = int(70 - i * 18 - self._pulse * 20)
            ring = QColor(accent)
            ring.setAlpha(max(0, a))
            p.setBrush(ring)
            p.setPen(Qt.NoPen)
            p.drawEllipse(QPoint(int(cx), int(cy)), int(r), int(r))

        # микрофон в центре
        core = QColor(accent)
        p.setBrush(core)
        p.drawEllipse(QPoint(int(cx), int(cy)), 14, 14)
        p.setPen(QColor("#ffffff"))
        f = self.font(); f.setPointSize(13); p.setFont(f)
        p.drawText(self.rect().adjusted(0, 0, 0, -(self.height()-90)),
                   Qt.AlignCenter, "🎤")
        p.end()

    def _center_top(self):
        screen = QGuiApplication.primaryScreen().availableGeometry()
        x = screen.center().x() - self.width() // 2
        y = screen.top() + 80
        self.move(x, y)

    def show_overlay(self):
        self._center_top()
        self.show()
        self.raise_()
        self._pulse_anim.start()
        # плавное появление
        eff = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(eff)
        a = QPropertyAnimation(eff, b"opacity", self)
        a.setDuration(180); a.setStartValue(0.0); a.setEndValue(1.0)
        a.start(QAbstractAnimation.DeleteWhenStopped)
        self._show_anim = a

    def hide_overlay(self):
        self._pulse_anim.stop()
        self.hide()


# ---------------------------------------------------------------------------
class Toast(QWidget):
    """Уведомление с текстом ответа ассистента (авто-скрытие)."""

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMinimumWidth(300)
        self.setMaximumWidth(440)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(12)

        self.icon = QLabel()
        self.icon.setPixmap(logo_pixmap(22))
        self.icon.setFixedSize(22, 22)
        layout.addWidget(self.icon, 0, Qt.AlignTop)

        self.text = QLabel("")
        self.text.setWordWrap(True)
        self.text.setStyleSheet(
            f"color: {Color.TEXT}; font-family: '{FONT_FAMILY}'; font-size: 13px;")
        layout.addWidget(self.text, 1)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._fade_out)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QColor(Color.CRUST))
        p.setPen(QColor(Color.SURFACE_1))
        p.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1),
                          Radius.MD, Radius.MD)
        # цветная полоса-акцент слева
        p.setBrush(QColor(Color.ACCENT))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(0, 8, 4, self.height() - 16, 2, 2)
        p.end()

    def _position(self):
        self.adjustSize()
        screen = QGuiApplication.primaryScreen().availableGeometry()
        x = screen.right() - self.width() - 24
        y = screen.bottom() - self.height() - 24
        self.move(x, y)

    def show_toast(self, message, duration=3800):
        self.text.setText(message)
        self._position()
        self.show()
        self.raise_()

        eff = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(eff)
        a = QPropertyAnimation(eff, b"opacity", self)
        a.setDuration(220); a.setStartValue(0.0); a.setEndValue(1.0)
        a.setEasingCurve(QEasingCurve.OutCubic)
        a.start(QAbstractAnimation.DeleteWhenStopped)
        self._in_anim = a

        self._hide_timer.start(duration)

    def _fade_out(self):
        eff = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(eff)
        a = QPropertyAnimation(eff, b"opacity", self)
        a.setDuration(280); a.setStartValue(1.0); a.setEndValue(0.0)
        a.setEasingCurve(QEasingCurve.InCubic)
        a.finished.connect(self.hide)
        a.start(QAbstractAnimation.DeleteWhenStopped)
        self._out_anim = a


# ---------------------------------------------------------------------------
class MicWidget(QWidget):
    """
    Плавающий мини-виджет микрофона для режима «всегда слушать».
    Клик переключает режим. Можно перетаскивать мышью.
    """

    clicked = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(58, 58)
        self._active = True
        self._drag = None
        self._pulse = 0.0

        self._anim = QPropertyAnimation(self, b"pulse", self)
        self._anim.setDuration(1100)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.InOutSine)
        self._anim.setLoopCount(-1)

    def get_pulse(self):
        return self._pulse

    def set_pulse(self, v):
        self._pulse = v
        self.update()

    pulse = Property(float, get_pulse, set_pulse)

    def set_active(self, on):
        self._active = on
        if on:
            self._anim.start()
        else:
            self._anim.stop()
            self._pulse = 0.0
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        cx, cy = self.width() / 2, self.height() / 2

        if self._active:
            ring = QColor(Color.ACCENT)
            ring.setAlpha(int(60 - self._pulse * 45))
            p.setBrush(ring); p.setPen(Qt.NoPen)
            p.drawEllipse(QPoint(int(cx), int(cy)),
                          int(26 + self._pulse * 4), int(26 + self._pulse * 4))
            fill = QColor(Color.ACCENT)
        else:
            fill = QColor(Color.SURFACE_1)

        p.setBrush(fill); p.setPen(Qt.NoPen)
        p.drawEllipse(QPoint(int(cx), int(cy)), 22, 22)

        p.setPen(QColor("#ffffff"))
        f = self.font(); f.setPointSize(15); p.setFont(f)
        p.drawText(self.rect(), Qt.AlignCenter, "🎤" if self._active else "🔇")
        p.end()

    def _corner(self):
        screen = QGuiApplication.primaryScreen().availableGeometry()
        self.move(screen.right() - self.width() - 24,
                  screen.bottom() - self.height() - 100)

    def show_widget(self):
        self._corner()
        self.set_active(True)
        self.show()
        self.raise_()

    # drag + click
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag = e.globalPosition().toPoint()
            self._moved = False

    def mouseMoveEvent(self, e):
        if self._drag is not None:
            delta = e.globalPosition().toPoint() - self._drag
            if abs(delta.x()) + abs(delta.y()) > 3:
                self._moved = True
            self.move(self.pos() + delta)
            self._drag = e.globalPosition().toPoint()

    def mouseReleaseEvent(self, e):
        was_click = self._drag is not None and not getattr(self, "_moved", False)
        self._drag = None
        if was_click:
            self.clicked.emit()
