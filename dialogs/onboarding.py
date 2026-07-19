"""
Экран приветствия при первом запуске.

Показывается один раз (флаг first_run). Даёт выбрать тему, акцент, слово
активации и режим озвучки. По завершении сохраняет настройки и применяет тему.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QWidget
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from core.i18n import t as tr
from core.theme import Color, FONT_FAMILY, Radius, theme_manager, PALETTES
from components.controls import styled_combo, styled_lineedit
from components.toggle_switch import ToggleSwitch
from core.settings_store import settings


class OnboardingDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setModal(True)
        self.setMinimumWidth(460)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._build()

    def _build(self):
        wrapper = QVBoxLayout(self)
        wrapper.setContentsMargins(0, 0, 0, 0)

        card = QWidget()
        card.setObjectName("onb")
        card.setStyleSheet(f"""
            QWidget#onb {{
                background: {Color.CRUST};
                border: 1px solid {Color.SURFACE_1};
                border-radius: {Radius.XL}px;
            }}
        """)
        wrapper.addWidget(card)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(34, 30, 34, 26)
        layout.setSpacing(16)

        # приветствие
        logo = QLabel("🌸")
        logo.setStyleSheet("font-size: 48px;")
        logo.setAlignment(Qt.AlignCenter)
        layout.addWidget(logo)

        title = QLabel(tr("Добро пожаловать в Rina"))
        title.setFont(QFont(FONT_FAMILY, 22, QFont.Bold))
        title.setStyleSheet(f"color: {Color.TEXT};")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        sub = QLabel(tr("Давайте быстро настроим ассистента под вас"))
        sub.setStyleSheet(f"color: {Color.OVERLAY}; font-size: 13px;")
        sub.setAlignment(Qt.AlignCenter)
        layout.addWidget(sub)
        layout.addSpacing(6)

        # тема
        layout.addWidget(self._label(tr("Тема оформления")))
        self.theme_combo = styled_combo(list(PALETTES.keys()), 0)
        self.theme_combo.currentTextChanged.connect(self._preview_theme)
        layout.addWidget(self.theme_combo)

        # акцент
        layout.addWidget(self._label(tr("Акцентный цвет")))
        self.accent_combo = styled_combo(
            list(PALETTES[theme_manager.theme]["accents"].keys()), 0)
        self.accent_combo.currentTextChanged.connect(self._preview_accent)
        layout.addWidget(self.accent_combo)

        # слово активации
        layout.addWidget(self._label(tr("Как обращаться к ассистенту")))
        self.wake_edit = styled_lineedit(tr("Рина"), tr("Рина"))
        layout.addWidget(self.wake_edit)

        # озвучка
        voice_row = QHBoxLayout()
        vlbl = QVBoxLayout()
        vlbl.setSpacing(2)
        vt = QLabel(tr("Отвечать голосом"))
        vt.setStyleSheet(f"color: {Color.TEXT}; font-size: 13px; font-weight: 600;")
        vd = QLabel(tr("Можно изменить позже в настройках"))
        vd.setStyleSheet(f"color: {Color.OVERLAY}; font-size: 11px;")
        vlbl.addWidget(vt)
        vlbl.addWidget(vd)
        voice_row.addLayout(vlbl, 1)
        self.voice_toggle = ToggleSwitch(checked=True)
        voice_row.addWidget(self.voice_toggle, 0, Qt.AlignVCenter)
        layout.addLayout(voice_row)

        layout.addSpacing(8)

        # кнопки
        btns = QHBoxLayout()
        skip = QPushButton(tr("Пропустить"))
        skip.setCursor(Qt.PointingHandCursor)
        skip.setFixedHeight(40)
        skip.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {Color.SUBTEXT};
                border: 1px solid {Color.SURFACE_1}; border-radius: {Radius.SM}px;
                padding: 4px 20px; font-size: 13px;
            }}
            QPushButton:hover {{ background: {Color.SURFACE_0}; }}
        """)
        skip.clicked.connect(self._finish)
        btns.addWidget(skip)
        btns.addStretch()

        start = QPushButton(tr("Начать  →"))
        start.setCursor(Qt.PointingHandCursor)
        start.setFixedHeight(40)
        start.setStyleSheet(f"""
            QPushButton {{
                background: {Color.ACCENT}; color: #ffffff;
                border: none; border-radius: {Radius.SM}px;
                padding: 4px 28px; font-size: 14px; font-weight: 600;
            }}
            QPushButton:hover {{ background: {Color.MAUVE}; }}
        """)
        start.clicked.connect(self._finish)
        btns.addWidget(start)
        layout.addLayout(btns)

    def _label(self, text):
        lbl = QLabel(text)
        lbl.setStyleSheet(f"color: {Color.SUBTEXT}; font-size: 12px; font-weight: 600;")
        return lbl

    def _preview_theme(self, name):
        # живой предпросмотр темы
        theme_manager.set_theme(name)
        # обновить список акцентов под новую палитру
        accents = list(PALETTES.get(name, {}).get("accents", {}).keys())
        cur = self.accent_combo.currentText()
        self.accent_combo.blockSignals(True)
        self.accent_combo.clear()
        self.accent_combo.addItems(accents)
        if cur in accents:
            self.accent_combo.setCurrentText(cur)
        self.accent_combo.blockSignals(False)

    def _preview_accent(self, name):
        if name:
            theme_manager.set_accent(name)

    def _finish(self):
        settings.update({
            "theme": self.theme_combo.currentText(),
            "accent": self.accent_combo.currentText(),
            "wake_word": self.wake_edit.text().strip() or tr("Рина"),
            "wake_words": [w.strip() for w in self.wake_edit.text().split(",")
                           if w.strip()] or [tr("Рина")],
            "voice_reply": self.voice_toggle.isChecked(),
            "first_run": False,
        })
        settings.save()
        theme_manager.apply(settings.get("theme"), settings.get("accent"))
        self.accept()
