"""
Вкладка «Напоминания»: таймеры, будильники и напоминания.

Основной способ поставить таймер — голосом («поставь таймер на 10 минут»),
здесь видно запланированное и можно добавить руками, когда говорить неудобно.
Список обновляется раз в секунду, чтобы «осталось» не устаревало на глазах.
"""

import time

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QPushButton
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont

from core.i18n import t as tr
from core.theme import Color, FONT_FAMILY, Radius
from components.card import Card
from components.controls import styled_lineedit, styled_combo, Divider
from core.settings_store import settings
from core.app_signals import app_signals
from voice import reminders as rem


class RemindersPage(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.store = rem.ReminderStore(settings)
        self._build()
        app_signals.reminders_changed.connect(self._reload)

        # «осталось» тикает — обновляем список раз в секунду
        self._tick = QTimer(self)
        self._tick.setInterval(1000)
        self._tick.timeout.connect(self._refresh_labels)
        self._tick.start()

    # ---------- построение ----------
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
        layout.setSpacing(18)

        layout.addLayout(self._header())
        layout.addWidget(self._add_card())

        self._list_holder = QVBoxLayout()
        self._list_holder.setSpacing(12)
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
        title = QLabel(tr("Напоминания"))
        title.setFont(QFont(FONT_FAMILY, 24, QFont.Bold))
        title.setStyleSheet(f"color: {Color.TEXT};")
        row.addWidget(title)

        self.count_label = QLabel("")
        self.count_label.setStyleSheet(
            f"color: {Color.OVERLAY}; font-size: 12px; padding-left: 4px;")
        row.addWidget(self.count_label, 0, Qt.AlignBottom)
        row.addStretch()

        self.clear_btn = QPushButton(tr("Отменить все"))
        self.clear_btn.setCursor(Qt.PointingHandCursor)
        self.clear_btn.setFixedHeight(34)
        self.clear_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {Color.RED};
                border: 1px solid {Color.alpha(Color.RED, '55')};
                border-radius: {Radius.SM}px;
                padding: 4px 16px; font-size: 12px; font-weight: 600;
            }}
            QPushButton:hover {{ background: {Color.alpha(Color.RED, '22')}; }}
        """)
        self.clear_btn.clicked.connect(self._clear_all)
        row.addWidget(self.clear_btn)

        sub = QLabel(tr("Скажите «поставь таймер на 10 минут» "
                        "или «напомни в 15:00 позвонить врачу»"))
        sub.setStyleSheet(f"color: {Color.OVERLAY}; font-size: 13px;")
        box.addLayout(row)
        box.addWidget(sub)
        return box

    # ---------- добавление вручную ----------
    def _add_card(self):
        card = Card()
        cl = card.layout()
        title = QLabel(tr("Новое напоминание"))
        title.setFont(QFont(FONT_FAMILY, 13, QFont.Bold))
        title.setStyleSheet(f"color: {Color.SUBTEXT};")
        cl.addWidget(title)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.text_edit = styled_lineedit(tr("О чём напомнить (необязательно)"))
        row.addWidget(self.text_edit, 1)

        self.amount_edit = styled_lineedit("10")
        self.amount_edit.setFixedWidth(70)
        self.amount_edit.setText("10")
        row.addWidget(self.amount_edit)

        self._unit_ids = ["минут", "секунд", "часов"]
        self.unit_combo = styled_combo(
            [tr("минут"), tr("секунд"), tr("часов")], 0)
        self.unit_combo.setFixedWidth(120)
        self.unit_combo.setMinimumWidth(110)
        row.addWidget(self.unit_combo)

        add_btn = QPushButton(tr("Поставить"))
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.setFixedHeight(38)
        add_btn.setStyleSheet(f"""
            QPushButton {{
                background: {Color.ACCENT}; color: #ffffff;
                border: none; border-radius: {Radius.SM}px;
                padding: 4px 20px; font-size: 13px; font-weight: 600;
            }}
            QPushButton:hover {{ background: {Color.alpha(Color.ACCENT, 'dd')}; }}
        """)
        add_btn.clicked.connect(self._add_manual)
        row.addWidget(add_btn)
        cl.addLayout(row)

        self.add_error = QLabel("")
        self.add_error.setStyleSheet(f"color: {Color.RED}; font-size: 11px;")
        self.add_error.hide()
        cl.addWidget(self.add_error)
        return card

    def _add_manual(self):
        raw = self.amount_edit.text().strip().replace(",", ".")
        try:
            amount = float(raw)
        except ValueError:
            amount = 0
        if amount <= 0:
            self.add_error.setText(tr("Укажите, через сколько напомнить."))
            self.add_error.show()
            return
        self.add_error.hide()

        factor = {"минут": 60, "секунд": 1, "часов": 3600}[
            self._unit_ids[self.unit_combo.currentIndex()]]
        text = self.text_edit.text().strip()
        self.store.add("reminder" if text else "timer",
                       time.time() + amount * factor, text)
        self.text_edit.clear()
        self._reload()

    # ---------- список ----------
    def _clear_list(self):
        while self._list_holder.count():
            item = self._list_holder.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def _reload(self):
        self._clear_list()
        self._rows = []

        items = sorted(self.store.active(), key=lambda r: r.get("fire_at", 0))
        self.count_label.setText(
            tr("активных: {count}", count=len(items)) if items else "")
        self.clear_btn.setVisible(bool(items))

        if not items:
            self._list_holder.addWidget(self._empty_card())
            return

        card = Card()
        cl = card.layout()
        for i, item in enumerate(items):
            row, label = self._item_row(item)
            self._rows.append((item, label))
            cl.addWidget(row)
            if i < len(items) - 1:
                cl.addWidget(Divider())
        self._list_holder.addWidget(card)

    def _item_row(self, item):
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 6, 0, 6)
        h.setSpacing(12)

        box = QVBoxLayout()
        box.setSpacing(2)
        titles = {"timer": tr("Таймер"), "reminder": tr("Напоминание"),
                  "alarm": tr("Будильник")}
        head = titles.get(item.get("kind"), tr("Напоминание"))
        if item.get("text"):
            head = f"{head}: {item['text']}"
        title = QLabel(head)
        title.setWordWrap(True)
        title.setStyleSheet(
            f"color: {Color.TEXT}; font-size: 13px; font-weight: 600;")
        left = QLabel(self._left_text(item))
        left.setStyleSheet(f"color: {Color.OVERLAY}; font-size: 11px;")
        box.addWidget(title)
        box.addWidget(left)
        h.addLayout(box, 1)

        cancel = QPushButton(tr("Отменить"))
        cancel.setCursor(Qt.PointingHandCursor)
        cancel.setFixedHeight(30)
        cancel.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {Color.RED};
                border: 1px solid {Color.alpha(Color.RED, '55')};
                border-radius: {Radius.SM}px;
                padding: 2px 14px; font-size: 12px; font-weight: 600;
            }}
            QPushButton:hover {{ background: {Color.alpha(Color.RED, '22')}; }}
        """)
        cancel.clicked.connect(
            lambda _checked=False, rid=item.get("id"): self._cancel(rid))
        h.addWidget(cancel, 0, Qt.AlignVCenter)
        return row, left

    def _left_text(self, item):
        fire_at = item.get("fire_at", 0)
        return tr("{when} · осталось {left}",
                  when=rem.when_text(fire_at),
                  left=rem.humanize_left(fire_at - time.time()))

    def _refresh_labels(self):
        """Обновляет только «осталось» — пересобирать список каждую секунду ни к чему."""
        for item, label in getattr(self, "_rows", []):
            label.setText(self._left_text(item))

    def _empty_card(self):
        card = Card()
        cl = card.layout()
        title = QLabel(tr("Ничего не запланировано"))
        title.setAlignment(Qt.AlignCenter)
        title.setFont(QFont(FONT_FAMILY, 15, QFont.Bold))
        title.setStyleSheet(f"color: {Color.TEXT};")
        desc = QLabel(tr("Таймеры и напоминания появятся здесь."))
        desc.setAlignment(Qt.AlignCenter)
        desc.setStyleSheet(f"color: {Color.SUBTEXT}; font-size: 13px;")
        cl.addSpacing(6)
        cl.addWidget(title)
        cl.addWidget(desc)
        cl.addSpacing(6)
        return card

    def _cancel(self, reminder_id):
        self.store.remove(reminder_id)
        self._reload()

    def _clear_all(self):
        self.store.clear_active()
        self._reload()


def build_reminders_page():
    return RemindersPage()
