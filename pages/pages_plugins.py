from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QPushButton
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from core.i18n import t as tr
from core.theme import Color, FONT_FAMILY, Radius
from components.card import Card
from components.toggle_switch import ToggleSwitch
from plugins.manager import plugin_manager, plugins_dir


class PluginsPage(QWidget):
    """Управление плагинами: список, включение/выключение, статус, ошибки."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build()
        plugin_manager.changed.connect(self._reload_list)
        plugin_manager.response.connect(self._on_response)

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
        self._layout = QVBoxLayout(container)
        self._layout.setContentsMargins(34, 28, 34, 28)
        self._layout.setSpacing(18)

        self._layout.addLayout(self._header())
        self._list_holder = QVBoxLayout()
        self._list_holder.setSpacing(14)
        self._layout.addLayout(self._list_holder)
        self._layout.addStretch()

        scroll.setWidget(container)
        outer.addWidget(scroll)

        self._reload_list()

    def _header(self):
        box = QVBoxLayout()
        box.setSpacing(4)
        row = QHBoxLayout()
        row.setSpacing(12)
        t = QLabel(tr("Плагины"))
        t.setFont(QFont(FONT_FAMILY, 24, QFont.Bold))
        t.setStyleSheet(f"color: {Color.TEXT};")
        row.addWidget(t)
        row.addStretch()

        refresh = QPushButton(tr("Обновить"))
        refresh.setCursor(Qt.PointingHandCursor)
        refresh.setFixedHeight(34)
        refresh.setStyleSheet(f"""
            QPushButton {{
                background: {Color.SURFACE_0}; color: {Color.TEXT};
                border: none; border-radius: {Radius.SM}px;
                padding: 4px 16px; font-size: 12px; font-weight: 600;
            }}
            QPushButton:hover {{ background: {Color.SURFACE_1}; }}
        """)
        refresh.clicked.connect(plugin_manager.discover)
        row.addWidget(refresh)

        sub = QLabel(tr("Папка плагинов: {p}", p=plugins_dir()))
        sub.setStyleSheet(f"color: {Color.OVERLAY}; font-size: 12px;")
        sub.setWordWrap(True)
        box.addLayout(row)
        box.addWidget(sub)
        return box

    def _clear_list(self):
        while self._list_holder.count():
            item = self._list_holder.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def _reload_list(self):
        self._clear_list()

        if not plugin_manager.plugins:
            empty = Card()
            lbl = QLabel(tr("Плагины не найдены"))
            lbl.setFont(QFont(FONT_FAMILY, 15, QFont.Bold))
            lbl.setStyleSheet(f"color: {Color.TEXT};")
            hint = QLabel(
                tr("Поместите папку плагина (с файлами plugin.json и main.py) ") +
                tr("в каталог plugins/ и нажмите «Обновить»."))
            hint.setWordWrap(True)
            hint.setStyleSheet(f"color: {Color.SUBTEXT}; font-size: 13px;")
            empty.layout().addWidget(lbl)
            empty.layout().addWidget(hint)
            self._list_holder.addWidget(empty)
            return

        for pid, lp in plugin_manager.plugins.items():
            self._list_holder.addWidget(self._plugin_card(pid, lp))

    def _plugin_card(self, pid, lp):
        card = Card()
        cl = card.layout()

        # шапка карточки
        top = QHBoxLayout()
        top.setSpacing(12)

        icon = QLabel(lp.manifest.icon)
        icon.setStyleSheet("font-size: 26px;")
        icon.setFixedWidth(36)
        top.addWidget(icon, 0, Qt.AlignTop)

        info = QVBoxLayout()
        info.setSpacing(3)
        name_row = QHBoxLayout()
        name_row.setSpacing(8)
        name = QLabel(lp.manifest.name)
        name.setFont(QFont(FONT_FAMILY, 14, QFont.Bold))
        name.setStyleSheet(f"color: {Color.TEXT};")
        name_row.addWidget(name)
        ver = QLabel(f"v{lp.manifest.version}")
        ver.setStyleSheet(f"""
            color: {Color.OVERLAY}; font-size: 11px;
            background: {Color.SURFACE_0}; border-radius: 6px; padding: 1px 8px;
        """)
        name_row.addWidget(ver)
        name_row.addStretch()
        info.addLayout(name_row)

        author = QLabel(tr("Автор: {a}", a=lp.manifest.author))
        author.setStyleSheet(f"color: {Color.OVERLAY}; font-size: 11px;")
        info.addWidget(author)

        desc = QLabel(lp.manifest.description or tr("Без описания"))
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {Color.SUBTEXT}; font-size: 12px;")
        info.addWidget(desc)
        top.addLayout(info, 1)

        # тумблер
        toggle = ToggleSwitch(checked=lp.enabled)
        toggle.setEnabled(lp.error is None or lp.instance is not None)
        toggle.toggled.connect(lambda on, p=pid: plugin_manager.toggle(p, on))
        top.addWidget(toggle, 0, Qt.AlignVCenter)

        cl.addLayout(top)

        # статус / ошибка
        if lp.error:
            err = QLabel(lp.error.split("\n")[0])
            err.setWordWrap(True)
            err.setStyleSheet(f"""
                color: {Color.RED}; font-size: 11px;
                background: {Color.alpha(Color.RED, '18')}; border-radius: {Radius.SM}px;
                padding: 8px 10px;
            """)
            cl.addWidget(err)
        else:
            state_row = QHBoxLayout()
            state_row.setSpacing(8)
            state = QLabel(tr("Включён") if lp.enabled else tr("Выключен"))
            color = Color.GREEN if lp.enabled else Color.OVERLAY
            state.setStyleSheet(f"color: {color}; font-size: 11px; font-weight: 600;")
            state_row.addWidget(state)

            # бейджи возможностей плагина
            if lp.enabled and lp.instance is not None:
                if plugin_manager._has_page(lp):
                    state_row.addWidget(self._badge(tr("вкладка"), Color.BLUE))
                if plugin_manager.has_settings_schema(lp):
                    state_row.addWidget(self._badge(tr("настройки"), Color.MAUVE))
            state_row.addStretch()
            wrap = QWidget()
            wrap.setLayout(state_row)
            cl.addWidget(wrap)

        return card

    def _badge(self, text, color):
        b = QLabel(text)
        b.setStyleSheet(f"""
            color: {color}; font-size: 10px; font-weight: 600;
            background: {Color.alpha(color, '22')}; border-radius: 6px; padding: 1px 8px;
        """)
        return b

    def _on_response(self, pid, text):
        # плагин что-то «ответил» — в реальном приложении сюда бы шёл вывод
        # ассистента; для демонстрации просто логируем в консоль.
        print(f"[plugin:{pid}] {text}")


def build_plugins_page():
    return PluginsPage()
