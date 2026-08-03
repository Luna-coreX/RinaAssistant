"""
Отрисовка декларативной вкладки плагина (API v2).

Это единственное место, где описание страницы превращается в Qt-виджеты.
Плагин про Qt ничего не знает — значит, ту же страницу сможет нарисовать
и другая оболочка, не переписывая плагины.

После действия (нажатия кнопки) страница пересобирается: плагин просто
описывает своё текущее состояние, а не следит за синхронизацией виджетов.
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QFrame
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from core.theme import Color, FONT_FAMILY, Radius


class PluginPageView(QWidget):
    def __init__(self, plugin_id, manager, parent=None):
        super().__init__(parent)
        self._plugin_id = plugin_id
        self._manager = manager

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(10)
        self.rebuild()

    # ---------- сборка ----------
    def rebuild(self):
        while self._layout.count():
            item = self._layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        for element in self._manager.get_plugin_page_spec(self._plugin_id):
            widget = self._render(element)
            if widget is not None:
                self._layout.addWidget(widget)

    def _render(self, element):
        kind = getattr(element, "kind", "")

        if kind == "title":
            lbl = QLabel(element.text)
            lbl.setFont(QFont(FONT_FAMILY, 14, QFont.Bold))
            lbl.setStyleSheet(f"color: {Color.TEXT};")
            return lbl

        if kind == "text":
            lbl = QLabel(element.text)
            lbl.setWordWrap(True)
            lbl.setStyleSheet(f"color: {Color.TEXT}; font-size: 13px;")
            return lbl

        if kind == "note":
            lbl = QLabel(element.text)
            lbl.setWordWrap(True)
            lbl.setStyleSheet(f"color: {Color.OVERLAY}; font-size: 11px;")
            return lbl

        if kind == "items":
            box = QWidget()
            lay = QVBoxLayout(box)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(4)
            for text in element.items or []:
                row = QLabel(text)
                row.setWordWrap(True)
                row.setStyleSheet(f"""
                    color: {Color.TEXT}; font-size: 12px;
                    background: {Color.SURFACE_0};
                    border-radius: {Radius.SM}px;
                    padding: 6px 10px;
                """)
                lay.addWidget(row)
            return box

        if kind == "button":
            btn = QPushButton(element.text)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedHeight(34)
            if element.variant == "danger":
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: transparent; color: {Color.RED};
                        border: 1px solid {Color.alpha(Color.RED, '55')};
                        border-radius: {Radius.SM}px;
                        padding: 4px 18px; font-size: 12px; font-weight: 600;
                    }}
                    QPushButton:hover {{
                        background: {Color.alpha(Color.RED, '22')};
                    }}
                """)
            else:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: {Color.SURFACE_0}; color: {Color.TEXT};
                        border: none; border-radius: {Radius.SM}px;
                        padding: 4px 18px; font-size: 12px; font-weight: 600;
                    }}
                    QPushButton:hover {{ background: {Color.SURFACE_1}; }}
                """)
            action = element.action
            btn.clicked.connect(lambda _checked=False, a=action: self._on_action(a))
            return btn

        if kind == "divider":
            line = QFrame()
            line.setFixedHeight(1)
            line.setStyleSheet(f"background: {Color.SURFACE_0}; border: none;")
            return line

        return None

    # ---------- действия ----------
    def _on_action(self, action):
        self._manager.dispatch_action(self._plugin_id, action)
        self.rebuild()      # состояние могло измениться — показываем актуальное
