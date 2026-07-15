from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QPushButton
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from core.i18n import t as tr
from core.theme import Color, FONT_FAMILY, Radius
from components.card import Card
from core.settings_store import settings
from core.app_signals import app_signals
from voice.history import HistoryStore

import time


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
        layout.setSpacing(14)

        layout.addLayout(self._header())
        self._list_holder = QVBoxLayout()
        self._list_holder.setSpacing(8)
        layout.addLayout(self._list_holder)
        layout.addStretch()

        scroll.setWidget(container)
        outer.addWidget(scroll)
        self._reload()

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
        row.addStretch()

        clear = QPushButton(tr("Очистить"))
        clear.setCursor(Qt.PointingHandCursor)
        clear.setFixedHeight(34)
        clear.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {Color.RED};
                border: 1px solid {Color.RED}55; border-radius: {Radius.SM}px;
                padding: 4px 16px; font-size: 12px; font-weight: 600;
            }}
            QPushButton:hover {{ background: {Color.RED}22; border: 1px solid {Color.RED}; }}
        """)
        clear.clicked.connect(self._clear_history)
        row.addWidget(clear)

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

        if not settings.get("save_history", True):
            self._list_holder.addWidget(self._notice(
                tr("Сохранение истории выключено"),
                tr("Включите «Сохранять историю» в настройках, чтобы вести журнал.")))
            return
        if not entries:
            self._list_holder.addWidget(self._notice(
                tr("История пуста"),
                tr("Здесь появятся ваши команды и ответы Рины.")))
            return

        # показываем последними снизу — новые внизу, как в чате
        last_day = None
        for e in entries:
            day = time.strftime("%d.%m.%Y", time.localtime(e.get("ts", 0)))
            if day != last_day:
                self._list_holder.addWidget(self._day_label(day))
                last_day = day
            self._list_holder.addWidget(self._bubble(e))

    def _day_label(self, day):
        lbl = QLabel(day)
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet(f"color: {Color.OVERLAY}; font-size: 11px; padding: 6px;")
        return lbl

    def _notice(self, title, desc):
        card = Card()
        t = QLabel(title)
        t.setFont(QFont(FONT_FAMILY, 15, QFont.Bold))
        t.setStyleSheet(f"color: {Color.TEXT};")
        d = QLabel(desc)
        d.setWordWrap(True)
        d.setStyleSheet(f"color: {Color.SUBTEXT}; font-size: 13px;")
        card.layout().addWidget(t)
        card.layout().addWidget(d)
        return card

    def _bubble(self, entry):
        kind = entry.get("kind", "user")
        text = entry.get("text", "")
        ts = entry.get("ts", 0)
        source = entry.get("source", "")
        clock = time.strftime("%H:%M", time.localtime(ts))

        is_user = (kind == "user")
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)

        bubble = QWidget()
        bl = QVBoxLayout(bubble)
        bl.setContentsMargins(14, 9, 14, 9)
        bl.setSpacing(3)

        top = QLabel((tr("🧑 Вы") if is_user else tr("🌸 Рина")) +
                     (f"  ·  {self._source_label(source)}" if source and is_user else ""))
        top.setStyleSheet(f"color: {Color.OVERLAY}; font-size: 10px; font-weight: 600;")
        bl.addWidget(top)

        msg = QLabel(text)
        msg.setWordWrap(True)
        msg.setStyleSheet(f"color: {Color.TEXT}; font-size: 13px;")
        bl.addWidget(msg)

        tm = QLabel(clock)
        tm.setStyleSheet(f"color: {Color.OVERLAY}; font-size: 9px;")
        tm.setAlignment(Qt.AlignRight)
        bl.addWidget(tm)

        # цвет пузыря: пользователь — акцент, ассистент — поверхность
        if is_user:
            bubble.setStyleSheet(f"""
                background: {Color.ACCENT}22;
                border: 1px solid {Color.ACCENT}44;
                border-radius: {Radius.MD}px;
            """)
        else:
            bubble.setStyleSheet(f"""
                background: {Color.CRUST};
                border: 1px solid {Color.SURFACE_0};
                border-radius: {Radius.MD}px;
            """)
        bubble.setMaximumWidth(560)

        # выравнивание: пользователь справа, Рина слева
        if is_user:
            h.addStretch()
            h.addWidget(bubble)
        else:
            h.addWidget(bubble)
            h.addStretch()
        return row

    def _source_label(self, source):
        return {"voice": "голос", "typed": "текст"}.get(source, source)

    def _clear_history(self):
        self.store.clear()
        self._reload()


def build_history_page():
    return HistoryPage()
