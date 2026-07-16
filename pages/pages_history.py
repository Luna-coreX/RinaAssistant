"""
Вкладка «История» — журнал взаимодействий в виде современного чата.

Сообщения пользователя и ответы Рины показаны пузырями с аватарами:
у ассистента — фирменная эмблема, у пользователя — силуэт. Записи
группируются по дням с разделителями «Сегодня»/«Вчера»/дата.
"""

from PySide6.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QPushButton,
    QSizePolicy,
)
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import (
    QFont, QPainter, QColor, QLinearGradient, QPainterPath, QPen,
)

from core.i18n import t as tr
from core.theme import Color, FONT_FAMILY, Radius
from core.assets import logo_pixmap
from components.card import Card
from core.settings_store import settings
from core.app_signals import app_signals
from animations.effects import fade_in
from voice.history import HistoryStore

import time


BUBBLE_MAX = 440
AVATAR = 34


def _rounded_path(rect: QRectF, tl, tr, br, bl) -> QPainterPath:
    """Прямоугольник со скруглениями, задаваемыми для каждого угла отдельно."""
    path = QPainterPath()
    path.moveTo(rect.left() + tl, rect.top())
    path.lineTo(rect.right() - tr, rect.top())
    path.arcTo(rect.right() - 2 * tr, rect.top(), 2 * tr, 2 * tr, 90, -90)
    path.lineTo(rect.right(), rect.bottom() - br)
    path.arcTo(rect.right() - 2 * br, rect.bottom() - 2 * br, 2 * br, 2 * br, 0, -90)
    path.lineTo(rect.left() + bl, rect.bottom())
    path.arcTo(rect.left(), rect.bottom() - 2 * bl, 2 * bl, 2 * bl, 270, -90)
    path.lineTo(rect.left(), rect.top() + tl)
    path.arcTo(rect.left(), rect.top(), 2 * tl, 2 * tl, 180, -90)
    path.closeSubpath()
    return path


class _Avatar(QWidget):
    """Кружок-аватар: эмблема Рины (ассистент) или силуэт (пользователь)."""

    def __init__(self, is_user, parent=None):
        super().__init__(parent)
        self._is_user = is_user
        self.setFixedSize(AVATAR, AVATAR)
        self._pix = None if is_user else logo_pixmap(AVATAR)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(0, 0, AVATAR, AVATAR)

        if self._is_user:
            grad = QLinearGradient(0, 0, AVATAR, AVATAR)
            grad.setColorAt(0.0, QColor(Color.ACCENT))
            grad.setColorAt(1.0, QColor(Color.ACCENT2))
            p.setBrush(grad)
            p.setPen(Qt.NoPen)
            p.drawEllipse(r)
            # силуэт человека
            p.setBrush(QColor("#ffffff"))
            hr = AVATAR * 0.15
            p.drawEllipse(QRectF(AVATAR / 2 - hr, AVATAR * 0.24, hr * 2, hr * 2))
            p.drawChord(QRectF(AVATAR * 0.24, AVATAR * 0.54,
                               AVATAR * 0.52, AVATAR * 0.5), 0, 180 * 16)
        else:
            # подложка + эмблема (она круглая, с прозрачным фоном)
            p.setBrush(QColor(Color.SURFACE_0))
            p.setPen(Qt.NoPen)
            p.drawEllipse(r)
            if self._pix is not None and not self._pix.isNull():
                p.drawPixmap(0, 0, self._pix)
            ring = QColor(Color.ACCENT)
            ring.setAlphaF(0.5)
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(ring, 1))
            p.drawEllipse(r.adjusted(0.5, 0.5, -0.5, -0.5))
        p.end()


class _Bubble(QFrame):
    """Пузырь сообщения с «хвостиком» и градиентом (у пользователя)."""

    def __init__(self, is_user, parent=None):
        super().__init__(parent)
        self._is_user = is_user
        self.setMaximumWidth(BUBBLE_MAX)
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 9, 14, 8)
        lay.setSpacing(3)
        self._lay = lay

    def layout(self):
        return self._lay

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        r = 14.0
        tail = 5.0
        if self._is_user:
            tl, tr_, br, bl = r, tail, r, r
        else:
            tl, tr_, br, bl = tail, r, r, r
        path = _rounded_path(rect, tl, tr_, br, bl)

        if self._is_user:
            grad = QLinearGradient(rect.topLeft(), rect.bottomRight())
            c1 = QColor(Color.ACCENT);  c1.setAlphaF(0.22)
            c2 = QColor(Color.ACCENT2); c2.setAlphaF(0.13)
            grad.setColorAt(0.0, c1)
            grad.setColorAt(1.0, c2)
            p.fillPath(path, grad)
            border = QColor(Color.ACCENT); border.setAlphaF(0.45)
        else:
            p.fillPath(path, QColor(Color.CRUST))
            border = QColor(Color.SURFACE_0)
        p.setPen(QPen(border, 1))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
        p.end()


class HistoryPage(QWidget):
    """Журнал взаимодействий: команды пользователя и ответы Рины."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.store = HistoryStore(settings)
        self._build()
        app_signals.history_changed.connect(self._reload)

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"""
            QScrollArea {{ background: transparent; border: none; }}
            QScrollBar:vertical {{ background: transparent; width: 8px; margin: 4px; }}
            QScrollBar::handle:vertical {{
                background: {Color.SURFACE_1}; border-radius: 4px; min-height: 30px; }}
            QScrollBar::handle:vertical:hover {{ background: {Color.SURFACE_2}; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(34, 28, 34, 28)
        layout.setSpacing(16)

        layout.addLayout(self._header())

        # обёртка списка — её и анимируем при обновлении
        self._list_wrap = QWidget()
        self._list_wrap.setStyleSheet("background: transparent;")
        self._list_holder = QVBoxLayout(self._list_wrap)
        self._list_holder.setContentsMargins(0, 0, 0, 0)
        self._list_holder.setSpacing(10)
        layout.addWidget(self._list_wrap)
        layout.addStretch()

        scroll.setWidget(container)
        outer.addWidget(scroll)
        self._reload()

    # ---------- шапка ----------
    def _header(self):
        box = QVBoxLayout()
        box.setSpacing(4)
        row = QHBoxLayout()
        row.setSpacing(12)
        ic = QLabel("🕑")
        ic.setStyleSheet("font-size: 30px;")
        t = QLabel(tr("История"))
        t.setFont(QFont(FONT_FAMILY, 24, QFont.Bold))
        t.setStyleSheet(f"color: {Color.TEXT};")
        row.addWidget(ic)
        row.addWidget(t)

        self.count_chip = QLabel("")
        self.count_chip.setStyleSheet(f"""
            color: {Color.SUBTEXT};
            background: {Color.alpha(Color.ACCENT, '1e')};
            border: 1px solid {Color.alpha(Color.ACCENT, '3a')};
            border-radius: 10px; padding: 3px 12px;
            font-size: 11px; font-weight: 700;
        """)
        row.addWidget(self.count_chip)
        row.addStretch()

        self.clear_btn = QPushButton(tr("🗑  Очистить"))
        self.clear_btn.setCursor(Qt.PointingHandCursor)
        self.clear_btn.setFixedHeight(34)
        self.clear_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {Color.RED};
                border: 1px solid {Color.alpha(Color.RED, '55')};
                border-radius: {Radius.SM}px;
                padding: 4px 16px; font-size: 12px; font-weight: 600;
            }}
            QPushButton:hover {{
                background: {Color.alpha(Color.RED, '22')};
                border: 1px solid {Color.RED};
            }}
            QPushButton:pressed {{ background: {Color.alpha(Color.RED, '33')}; }}
        """)
        self.clear_btn.clicked.connect(self._clear_history)
        row.addWidget(self.clear_btn)

        sub = QLabel(tr("Команды и ответы ассистента"))
        sub.setStyleSheet(f"color: {Color.OVERLAY}; font-size: 13px;")
        box.addLayout(row)
        box.addWidget(sub)
        return box

    def _clear_list(self):
        while self._list_holder.count():
            item = self._list_holder.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def _reload(self):
        self._clear_list()
        entries = self.store.all()

        # счётчик в шапке
        if entries and settings.get("save_history", True):
            n = len(entries)
            self.count_chip.setText(self._plural(n))
            self.count_chip.show()
        else:
            self.count_chip.hide()

        if not settings.get("save_history", True):
            self._list_holder.addWidget(self._empty_state(
                "🔕",
                tr("Сохранение истории выключено"),
                tr("Включите «Сохранять историю» в настройках, чтобы вести журнал.")))
            self._animate_list()
            return
        if not entries:
            self._list_holder.addWidget(self._empty_state(
                "🕑",
                tr("История пуста"),
                tr("Здесь появятся ваши команды и ответы Рины.")))
            self._animate_list()
            return

        last_day = None
        for e in entries:
            day = self._day_title(e.get("ts", 0))
            if day != last_day:
                self._list_holder.addWidget(self._day_separator(day))
                last_day = day
            self._list_holder.addWidget(self._bubble_row(e))
        self._animate_list()

    def _animate_list(self):
        fade_in(self._list_wrap, duration=300)

    # ---------- разделитель дня ----------
    def _day_separator(self, day):
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 8, 0, 2)
        h.setSpacing(12)
        h.addWidget(self._hline(), 1)
        pill = QLabel(day)
        pill.setStyleSheet(f"""
            color: {Color.SUBTEXT};
            background: {Color.CRUST};
            border: 1px solid {Color.SURFACE_0};
            border-radius: 10px; padding: 3px 14px;
            font-size: 11px; font-weight: 700;
        """)
        h.addWidget(pill)
        h.addWidget(self._hline(), 1)
        return w

    def _hline(self):
        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet(f"background: {Color.SURFACE_0}; border: none;")
        return line

    # ---------- пустое состояние ----------
    def _empty_state(self, glyph, title, desc):
        card = Card()
        cl = card.layout()
        cl.setSpacing(8)
        icon = QLabel(glyph)
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet("font-size: 42px;")
        t = QLabel(title)
        t.setAlignment(Qt.AlignCenter)
        t.setFont(QFont(FONT_FAMILY, 15, QFont.Bold))
        t.setStyleSheet(f"color: {Color.TEXT};")
        d = QLabel(desc)
        d.setAlignment(Qt.AlignCenter)
        d.setWordWrap(True)
        d.setStyleSheet(f"color: {Color.SUBTEXT}; font-size: 13px;")
        cl.addSpacing(6)
        cl.addWidget(icon)
        cl.addWidget(t)
        cl.addWidget(d)
        cl.addSpacing(6)
        return card

    # ---------- пузырь сообщения ----------
    def _bubble_row(self, entry):
        kind = entry.get("kind", "user")
        text = entry.get("text", "")
        ts = entry.get("ts", 0)
        source = entry.get("source", "")
        clock = time.strftime("%H:%M", time.localtime(ts))
        is_user = (kind == "user")

        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(10)
        h.setAlignment(Qt.AlignTop)

        avatar = _Avatar(is_user)
        bubble = _Bubble(is_user)
        bl = bubble.layout()

        who = tr("Вы") if is_user else "Rina"
        meta = who
        if source and is_user:
            meta += f"  ·  {self._source_label(source)}"
        top = QLabel(meta)
        top.setStyleSheet(
            f"color: {Color.ACCENT if is_user else Color.MAUVE}; "
            f"font-size: 10px; font-weight: 700; background: transparent;")
        bl.addWidget(top)

        msg = QLabel(text)
        msg.setWordWrap(True)
        msg.setStyleSheet(
            f"color: {Color.TEXT}; font-size: 13px; background: transparent;")
        bl.addWidget(msg)

        tm = QLabel(clock)
        tm.setStyleSheet(
            f"color: {Color.OVERLAY}; font-size: 9px; background: transparent;")
        tm.setAlignment(Qt.AlignRight)
        bl.addWidget(tm)

        if is_user:
            h.addStretch()
            h.addWidget(bubble)
            h.addWidget(avatar)
        else:
            h.addWidget(avatar)
            h.addWidget(bubble)
            h.addStretch()
        return row

    # ---------- вспомогательное ----------
    def _source_label(self, source):
        return {"voice": tr("голос"), "typed": tr("текст")}.get(source, source)

    def _day_title(self, ts):
        day = time.strftime("%d.%m.%Y", time.localtime(ts))
        today = time.strftime("%d.%m.%Y", time.localtime())
        yday = time.strftime("%d.%m.%Y", time.localtime(time.time() - 86400))
        if day == today:
            return tr("Сегодня")
        if day == yday:
            return tr("Вчера")
        return day

    def _plural(self, n):
        # согласование «запись/записи/записей»
        n10, n100 = n % 10, n % 100
        if n10 == 1 and n100 != 11:
            word = tr("запись")
        elif 2 <= n10 <= 4 and not (12 <= n100 <= 14):
            word = tr("записи")
        else:
            word = tr("записей")
        return f"{n} {word}"

    def _clear_history(self):
        self.store.clear()
        self._reload()


def build_history_page():
    return HistoryPage()
