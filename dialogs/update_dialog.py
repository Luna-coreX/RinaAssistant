"""
Окно «Доступно обновление».

Показывается при запуске, когда автопроверка нашла новую версию. Раньше для
этого использовалось только всплывающее уведомление трея, но оно молча
пропадает, если иконка трея скрыта (выключено «Сворачивать в трей»), — поэтому
основной способ сообщить об обновлении именно окно.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
)
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QFont, QDesktopServices

from core.i18n import t as tr
from core.theme import Color, FONT_FAMILY, Radius
from core.assets import logo_pixmap
from version import LINKS


def releases_url() -> str:
    """Страница релизов проекта (fallback — сайт/репозиторий)."""
    source = LINKS.get("source") or ""
    if source:
        return source.rstrip("/") + "/releases/latest"
    return LINKS.get("site") or ""


class UpdateDialog(QDialog):
    def __init__(self, message, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Доступно обновление"))
        self.setModal(False)          # не блокируем работу с приложением
        self.setMinimumWidth(420)
        self.setStyleSheet(f"QDialog {{ background: {Color.BASE}; }}")
        self._build(message)

    def _build(self, message):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 24, 26, 22)
        layout.setSpacing(14)

        # шапка: эмблема + заголовок
        head = QHBoxLayout()
        head.setSpacing(14)
        logo = QLabel()
        logo.setPixmap(logo_pixmap(48))
        logo.setFixedSize(48, 48)
        logo.setAlignment(Qt.AlignCenter)
        head.addWidget(logo)

        titles = QVBoxLayout()
        titles.setSpacing(2)
        title = QLabel(tr("Доступно обновление"))
        title.setFont(QFont(FONT_FAMILY, 17, QFont.Bold))
        title.setStyleSheet(f"color: {Color.TEXT};")
        titles.addWidget(title)
        sub = QLabel(message)
        sub.setWordWrap(True)
        sub.setStyleSheet(f"color: {Color.SUBTEXT}; font-size: 13px;")
        titles.addWidget(sub)
        head.addLayout(titles, 1)
        layout.addLayout(head)

        # кнопки
        btns = QHBoxLayout()
        btns.addStretch()

        later = QPushButton(tr("Позже"))
        later.setCursor(Qt.PointingHandCursor)
        later.setFixedHeight(38)
        later.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {Color.SUBTEXT};
                border: 1px solid {Color.SURFACE_1}; border-radius: {Radius.SM}px;
                padding: 4px 20px; font-size: 13px;
            }}
            QPushButton:hover {{ background: {Color.SURFACE_0}; }}
        """)
        later.clicked.connect(self.reject)

        download = QPushButton(tr("Скачать"))
        download.setCursor(Qt.PointingHandCursor)
        download.setFixedHeight(38)
        download.setStyleSheet(f"""
            QPushButton {{
                background: {Color.gradient(0, 0, 1, 0)}; color: #ffffff;
                border: none; border-radius: {Radius.SM}px;
                padding: 4px 24px; font-size: 13px; font-weight: 700;
            }}
            QPushButton:hover {{
                background: {Color.gradient(0, 0, 1, 0, tri=True)};
            }}
        """)
        download.clicked.connect(self._open_releases)

        btns.addWidget(later)
        btns.addWidget(download)
        layout.addLayout(btns)

    def _open_releases(self):
        url = releases_url()
        if url:
            QDesktopServices.openUrl(QUrl(url))
        self.accept()
