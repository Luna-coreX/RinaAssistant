from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from core.i18n import t as tr
from core.theme import Color, FONT_FAMILY, Radius
from components.card import Card
from components.controls import Divider
from components.key_capture import KeyCaptureEdit
from core.settings_store import settings
from core.app_signals import app_signals
from voice.hotkey_actions import HOTKEY_ACTIONS


class HotkeysPage(QWidget):
    """Назначение горячих клавиш действиям."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build()

        # живой статус глобального хоткея (из кэша + подписка на обновления)
        self._update_global_status(app_signals.last_hotkey_global)
        app_signals.hotkey_status.connect(self._update_global_status)

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

        # основной хоткей «слушать»
        main_card = Card()
        mc = main_card.layout()
        mtitle = QLabel(tr("Основная клавиша"))
        mtitle.setFont(QFont(FONT_FAMILY, 13, QFont.Bold))
        mtitle.setStyleSheet(f"color: {Color.SUBTEXT};")
        mc.addWidget(mtitle)
        self.main_capture = KeyCaptureEdit(settings.get("hotkey", "Ctrl+Shift+R"))
        self.main_capture.captured.connect(self._on_main_changed)
        mc.addWidget(self._action_row(
            tr("Активация ассистента"),
            tr("Разовое распознавание речи"), self.main_capture))

        # живой индикатор: работает ли глобальный вызов (даже из трея)
        self.global_status = QLabel("")
        self.global_status.setWordWrap(True)
        mc.addWidget(self.global_status)
        layout.addWidget(main_card)

        # дополнительные действия
        actions_card = Card()
        ac = actions_card.layout()
        atitle = QLabel(tr("Дополнительные действия"))
        atitle.setFont(QFont(FONT_FAMILY, 13, QFont.Bold))
        atitle.setStyleSheet(f"color: {Color.SUBTEXT};")
        ac.addWidget(atitle)

        saved = settings.get("action_hotkeys", {}) or {}
        self._captures = {}
        items = list(HOTKEY_ACTIONS.items())
        for i, (action_id, (label, desc, _icon)) in enumerate(items):
            cap = KeyCaptureEdit(saved.get(action_id, ""))
            cap.captured.connect(
                lambda seq, aid=action_id: self._on_action_changed(aid, seq))
            self._captures[action_id] = cap
            ac.addWidget(self._action_row(label, desc, cap))
            if i < len(items) - 1:
                ac.addWidget(Divider())
        layout.addWidget(actions_card)

        hint = QLabel(
            tr("Кликните по полю и нажмите нужную комбинацию. "
               "Esc — отмена, пустое поле — снять назначение."))
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {Color.OVERLAY}; font-size: 11px;")
        layout.addWidget(hint)

        layout.addStretch()
        scroll.setWidget(container)
        outer.addWidget(scroll)

    def _header(self):
        box = QVBoxLayout()
        box.setSpacing(4)
        row = QHBoxLayout()
        row.setSpacing(12)
        t = QLabel(tr("Горячие клавиши"))
        t.setFont(QFont(FONT_FAMILY, 24, QFont.Bold))
        t.setStyleSheet(f"color: {Color.TEXT};")
        row.addWidget(t)
        row.addStretch()
        sub = QLabel(tr("Быстрый доступ к действиям ассистента"))
        sub.setStyleSheet(f"color: {Color.OVERLAY}; font-size: 13px;")
        box.addLayout(row)
        box.addWidget(sub)
        return box

    def _action_row(self, title, desc, capture):
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(2, 8, 2, 8)
        h.setSpacing(14)
        box = QVBoxLayout()
        box.setSpacing(2)
        t = QLabel(title)
        t.setFont(QFont(FONT_FAMILY, 12, QFont.Bold))
        t.setStyleSheet(f"color: {Color.TEXT};")
        d = QLabel(desc)
        d.setStyleSheet(f"color: {Color.OVERLAY}; font-size: 11px;")
        box.addWidget(t)
        box.addWidget(d)
        h.addLayout(box, 1)
        h.addWidget(capture, 0, Qt.AlignVCenter)
        return w

    def _update_global_status(self, global_ok: bool):
        if global_ok:
            self.global_status.setText(
                tr("Глобальный вызов активен — работает даже из трея."))
            self.global_status.setStyleSheet(
                f"color: {Color.GREEN}; font-size: 11px; padding-left: 42px;")
        else:
            self.global_status.setText(
                tr("Глобальный вызов недоступен (нужен пакет pynput: ") +
                tr("pip install pynput). Комбинация сработает, когда окно в фокусе."))
            self.global_status.setStyleSheet(
                f"color: {Color.OVERLAY}; font-size: 11px; padding-left: 42px;")

    def _on_main_changed(self, seq):
        settings.set("hotkey", seq)
        settings.save()
        app_signals.hotkey_changed.emit()

    def _on_action_changed(self, action_id, seq):
        actions = dict(settings.get("action_hotkeys", {}) or {})
        if seq:
            actions[action_id] = seq
        else:
            actions.pop(action_id, None)
        settings.set("action_hotkeys", actions)
        settings.save()
        app_signals.hotkey_changed.emit()


def build_hotkeys_page():
    return HotkeysPage()
