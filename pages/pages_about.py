from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QPushButton
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QDesktopServices
from PySide6.QtCore import QUrl

from core.i18n import t as tr
from core.theme import Color, FONT_FAMILY, Radius
from core.assets import logo_pixmap
from components.card import Card
from version import APP_VERSION, BUILD, LINKS


class AboutPage(QWidget):
    """О программе: версия, ссылки, стек, благодарности."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build()

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
        layout.setSpacing(20)

        layout.addWidget(self._hero())
        layout.addWidget(self._links_card())
        layout.addWidget(self._tech_card())
        layout.addWidget(self._credits_card())
        layout.addStretch()

        scroll.setWidget(container)
        outer.addWidget(scroll)

    def _hero(self):
        card = Card()
        cl = card.layout()
        cl.setSpacing(6)

        logo = QLabel()
        logo.setPixmap(logo_pixmap(96))
        logo.setAlignment(Qt.AlignCenter)
        cl.addWidget(logo)

        name = QLabel("Rina Assistant")
        name.setFont(QFont(FONT_FAMILY, 26, QFont.Bold))
        name.setStyleSheet(f"color: {Color.TEXT};")
        name.setAlignment(Qt.AlignCenter)
        cl.addWidget(name)

        ver = QLabel(tr("Версия {v}  ·  сборка {b}", v=APP_VERSION, b=BUILD))
        ver.setStyleSheet(f"color: {Color.SUBTEXT}; font-size: 13px;")
        ver.setAlignment(Qt.AlignCenter)
        cl.addWidget(ver)

        tag = QLabel(tr("Персональный голосовой ассистент с открытой системой плагинов"))
        tag.setWordWrap(True)
        tag.setStyleSheet(f"color: {Color.OVERLAY}; font-size: 12px;")
        tag.setAlignment(Qt.AlignCenter)
        cl.addWidget(tag)

        return card

    def _link_button(self, text, url):
        btn = QPushButton(text)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFixedHeight(42)
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {Color.SURFACE_0}; color: {Color.TEXT};
                border: none; border-radius: {Radius.SM}px;
                text-align: left; padding: 0 16px; font-size: 13px;
            }}
            QPushButton:hover {{ background: {Color.SURFACE_1}; }}
        """)
        btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(url)))
        return btn

    def _links_card(self):
        card = Card()
        cl = card.layout()
        title = QLabel(tr("Ссылки"))
        title.setFont(QFont(FONT_FAMILY, 13, QFont.Bold))
        title.setStyleSheet(f"color: {Color.SUBTEXT};")
        cl.addWidget(title)

        # показываем только те ссылки, у которых задан URL (пустые — пропускаем)
        link_specs = [
            (tr("Веб-сайт"), LINKS.get("site")),
            (tr("Исходный код"), LINKS.get("source")),
            (tr("Документация"), LINKS.get("docs")),
            (tr("Сообщить об ошибке"), LINKS.get("issues")),
        ]
        for text, url in link_specs:
            if url:
                cl.addWidget(self._link_button(text, url))
        return card

    def _tech_card(self):
        card = Card()
        cl = card.layout()
        title = QLabel(tr("Технологии"))
        title.setFont(QFont(FONT_FAMILY, 13, QFont.Bold))
        title.setStyleSheet(f"color: {Color.SUBTEXT};")
        cl.addWidget(title)

        rows = [
            (tr("Интерфейс"), "PySide6 (Qt for Python)"),
            (tr("Язык"), "Python 3"),
            (tr("Горячие клавиши"), tr("pynput (опционально)")),
            (tr("Темы"), tr("5 палитр, живое переключение")),
            (tr("Плагины"), tr("открытый API, горячая загрузка")),
        ]
        for k, v in rows:
            row = QHBoxLayout()
            key = QLabel(k)
            key.setStyleSheet(f"color: {Color.SUBTEXT}; font-size: 12px;")
            key.setFixedWidth(150)
            val = QLabel(v)
            val.setStyleSheet(f"color: {Color.TEXT}; font-size: 12px; font-weight: 600;")
            val.setWordWrap(True)
            row.addWidget(key)
            row.addWidget(val, 1)
            cl.addLayout(row)
        return card

    def _credits_card(self):
        card = Card()
        cl = card.layout()
        title = QLabel(tr("Благодарности"))
        title.setFont(QFont(FONT_FAMILY, 13, QFont.Bold))
        title.setStyleSheet(f"color: {Color.SUBTEXT};")
        cl.addWidget(title)

        text = QLabel(
            tr("Цветовые палитры вдохновлены темами Catppuccin, Tokyo Night, ") +
            tr("Nord и Dracula. Спасибо сообществу открытого ПО."))
        text.setWordWrap(True)
        text.setStyleSheet(f"color: {Color.SUBTEXT}; font-size: 12px;")
        cl.addWidget(text)

        copy = QLabel(tr("Rina Assistant — часть NeuroSync Foundry. © 2026 Luna-coreX. Лицензия Apache 2.0."))
        copy.setStyleSheet(f"color: {Color.OVERLAY}; font-size: 11px;")
        cl.addWidget(copy)
        return card


def build_about_page():
    return AboutPage()
