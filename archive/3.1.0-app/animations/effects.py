"""
Аниматоры интерфейса.

Важно: windowOpacity работает ТОЛЬКО у окон (QMainWindow/QDialog).
Для обычных виджетов (страницы, карточки) используем
QGraphicsOpacityEffect + анимацию его свойства opacity.
"""

from PySide6.QtCore import (
    QPropertyAnimation,
    QEasingCurve,
    QPoint,
    QParallelAnimationGroup,
    QAbstractAnimation,
    QObject,
    Property,
)
from PySide6.QtWidgets import QWidget, QGraphicsOpacityEffect


# Единая «фирменная» кривая — мягкий, но энергичный выход (модно/футуристично).
EASE = QEasingCurve.OutExpo


def _opacity_effect(widget: QWidget) -> QGraphicsOpacityEffect:
    """Достаём (или создаём) эффект прозрачности для виджета."""
    effect = widget.graphicsEffect()
    if not isinstance(effect, QGraphicsOpacityEffect):
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
    return effect


def fade_in(widget: QWidget, duration: int = 350,
            start: float = 0.0, end: float = 1.0):
    """Плавное появление через QGraphicsOpacityEffect."""
    effect = _opacity_effect(widget)
    effect.setOpacity(start)

    anim = QPropertyAnimation(effect, b"opacity", widget)
    anim.setDuration(duration)
    anim.setStartValue(start)
    anim.setEndValue(end)
    anim.setEasingCurve(EASE)
    anim.start(QAbstractAnimation.DeleteWhenStopped)

    widget._fade_anim = anim  # держим ссылку, иначе GC убьёт анимацию
    return anim


def fade_window_in(window: QWidget, duration: int = 450):
    """Появление именно окна — тут корректно работает windowOpacity."""
    anim = QPropertyAnimation(window, b"windowOpacity", window)
    anim.setDuration(duration)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setEasingCurve(QEasingCurve.OutCubic)
    anim.start(QAbstractAnimation.DeleteWhenStopped)
    window._win_fade_anim = anim
    return anim


def slide_in(widget: QWidget, duration: int = 300,
             offset: int = 26, direction: str = "up"):
    """Появление со смещением (по умолчанию снизу вверх)."""
    end_pos = widget.pos()

    dx, dy = 0, 0
    if direction == "up":
        dy = offset
    elif direction == "down":
        dy = -offset
    elif direction == "left":
        dx = offset
    elif direction == "right":
        dx = -offset

    start_pos = QPoint(end_pos.x() + dx, end_pos.y() + dy)
    widget.move(start_pos)

    anim = QPropertyAnimation(widget, b"pos", widget)
    anim.setDuration(duration)
    anim.setStartValue(start_pos)
    anim.setEndValue(end_pos)
    anim.setEasingCurve(QEasingCurve.OutCubic)
    anim.start(QAbstractAnimation.DeleteWhenStopped)

    widget._slide_anim = anim
    return anim


def page_transition(widget: QWidget, duration: int = 280, offset: int = 26):
    """
    Переход для страниц: fade + лёгкий сдвиг слева.

    Карточки теперь рисуют тень сами (без QGraphicsDropShadowEffect),
    поэтому opacity-эффект на странице их больше не ломает.
    """
    effect = _opacity_effect(widget)
    effect.setOpacity(0.0)

    end_pos = widget.pos()
    start_pos = QPoint(end_pos.x() + offset, end_pos.y())
    widget.move(start_pos)

    fade = QPropertyAnimation(effect, b"opacity", widget)
    fade.setDuration(duration)
    fade.setStartValue(0.0)
    fade.setEndValue(1.0)
    fade.setEasingCurve(EASE)

    move = QPropertyAnimation(widget, b"pos", widget)
    move.setDuration(duration)
    move.setStartValue(start_pos)
    move.setEndValue(end_pos)
    move.setEasingCurve(EASE)

    group = QParallelAnimationGroup(widget)
    group.addAnimation(fade)
    group.addAnimation(move)
    group.start(QAbstractAnimation.DeleteWhenStopped)

    widget._page_anim = group
    return group


class PulseValue(QObject):
    """
    Источник плавно пульсирующего значения 0→1→0 (loop).

    Используется для «дыхания» индикаторов/свечения. Виджет подписывается
    на сигнал :attr:`tick` и перерисовывается. Значение доступно как
    свойство ``value`` (для отладки/цепочек).
    """

    def __init__(self, duration: int = 1600, parent=None):
        super().__init__(parent)
        self._value = 0.0
        self._anim = QPropertyAnimation(self, b"value", self)
        self._anim.setDuration(duration)
        self._anim.setStartValue(0.0)
        self._anim.setKeyValueAt(0.5, 1.0)
        self._anim.setEndValue(0.0)
        self._anim.setEasingCurve(QEasingCurve.InOutSine)
        self._anim.setLoopCount(-1)

    def get_value(self):
        return self._value

    def set_value(self, v):
        self._value = v
        for cb in getattr(self, "_subs", []):
            cb()

    value = Property(float, get_value, set_value)

    def subscribe(self, callback):
        self._subs = getattr(self, "_subs", [])
        self._subs.append(callback)

    def start(self):
        self._anim.start()

    def stop(self):
        self._anim.stop()
