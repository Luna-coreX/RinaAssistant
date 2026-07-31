from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGridLayout, QPushButton
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from core.i18n import t as tr
from core.theme import Color, FONT_FAMILY, Radius, PAGE_ICONS
from components.card import Card


def _header(title, subtitle, icon):
    box = QVBoxLayout()
    box.setSpacing(4)

    row = QHBoxLayout()
    row.setSpacing(12)
    t = QLabel(title)
    t.setFont(QFont(FONT_FAMILY, 24, QFont.Bold))
    t.setStyleSheet(f"color: {Color.TEXT};")
    row.addWidget(t)
    row.addStretch()

    sub = QLabel(subtitle)
    sub.setStyleSheet(f"color: {Color.OVERLAY}; font-size: 13px;")

    box.addLayout(row)
    box.addWidget(sub)
    return box


def build_page(name: str) -> QWidget:
    if name == "Рина":
        from .pages_rina import RinaPage
        return RinaPage()

    if name == "Настройки":
        from .pages_settings import SettingsPage
        return SettingsPage()

    if name == "О программе":
        from .pages_about import build_about_page
        return build_about_page()

    if name == "Плагины":
        from .pages_plugins import build_plugins_page
        return build_plugins_page()

    if name == "Команды":
        from .pages_commands import build_commands_page
        return build_commands_page()

    if name == "Горячие клавиши":
        from .pages_hotkeys import build_hotkeys_page
        return build_hotkeys_page()

    if name == "История":
        from .pages_history import build_history_page
        return build_history_page()

    # запасная страница для неизвестного имени (все штатные вкладки — выше)
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(34, 28, 34, 28)
    layout.setSpacing(22)
    icon = PAGE_ICONS.get(name, "•")
    layout.addLayout(_header(name, tr("Раздел"), icon))
    layout.addStretch()
    return page

