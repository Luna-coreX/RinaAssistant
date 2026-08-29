"""
Отрисовка декларативной вкладки плагина (API v2).

Это единственное место, где описание страницы превращается в Qt-виджеты.
Плагин про Qt ничего не знает — значит, ту же страницу сможет нарисовать
и другая оболочка, не переписывая плагины.

После действия (нажатия кнопки) страница пересобирается: плагин просто
описывает своё текущее состояние, а не следит за синхронизацией виджетов.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame
)
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

    @staticmethod
    def _plain(label):
        """Плагин задаёт текст сам — рисуем его как текст, а не как разметку."""
        label.setTextFormat(Qt.PlainText)
        return label

    def _render(self, element):
        kind = getattr(element, "kind", "")

        if kind == "title":
            lbl = self._plain(QLabel(element.text))
            lbl.setFont(QFont(FONT_FAMILY, 14, QFont.Bold))
            lbl.setStyleSheet(f"color: {Color.TEXT};")
            return lbl

        if kind == "text":
            lbl = self._plain(QLabel(element.text))
            lbl.setWordWrap(True)
            lbl.setStyleSheet(f"color: {Color.TEXT}; font-size: 13px;")
            return lbl

        if kind == "note":
            lbl = self._plain(QLabel(element.text))
            lbl.setWordWrap(True)
            lbl.setStyleSheet(f"color: {Color.OVERLAY}; font-size: 11px;")
            return lbl

        if kind == "items":
            box = QWidget()
            lay = QVBoxLayout(box)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(4)
            for text in element.items or []:
                row = self._plain(QLabel(text))
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

        if kind == "input":
            return self._render_input(element)

        if kind == "table":
            return self._render_table(element)

        if kind == "progress":
            return self._render_progress(element)

        if kind == "badge":
            colors = {"good": Color.GREEN, "warn": Color.PEACH,
                      "danger": Color.RED, "normal": Color.SUBTEXT}
            color = colors.get(element.variant, Color.SUBTEXT)
            lbl = self._plain(QLabel(element.text))
            lbl.setStyleSheet(f"""
                color: {color};
                background: {Color.alpha(color, '1e')};
                border-radius: {Radius.SM}px;
                padding: 3px 10px; font-size: 11px; font-weight: 600;
            """)
            lbl.setAlignment(Qt.AlignLeft)
            row = QWidget()
            lay = QHBoxLayout(row)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.addWidget(lbl)
            lay.addStretch()
            return row

        if kind == "divider":
            line = QFrame()
            line.setFixedHeight(1)
            line.setStyleSheet(f"background: {Color.SURFACE_0}; border: none;")
            return line

        return None

    def _render_input(self, element):
        from components.controls import styled_lineedit

        box = QWidget()
        lay = QHBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        edit = styled_lineedit(element.text, str(element.value or ""))
        action = element.action

        def submit():
            text = edit.text().strip()
            if text:
                self._on_action(action, text)

        edit.returnPressed.connect(submit)
        lay.addWidget(edit, 1)

        if element.variant:          # подпись кнопки, если плагин её задал
            btn = QPushButton(element.variant)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedHeight(38)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {Color.ACCENT}; color: #ffffff;
                    border: none; border-radius: {Radius.SM}px;
                    padding: 4px 18px; font-size: 12px; font-weight: 600;
                }}
                QPushButton:hover {{ background: {Color.alpha(Color.ACCENT, 'dd')}; }}
            """)
            btn.clicked.connect(submit)
            lay.addWidget(btn)
        return box

    def _render_table(self, element):
        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)

        headers = element.value if isinstance(element.value, list) else None
        if headers:
            lay.addWidget(self._table_row(headers, header=True))
        for row in element.items or []:
            lay.addWidget(self._table_row(row))
        return box

    def _table_row(self, cells, header=False):
        row = QWidget()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(10, 5, 10, 5)
        lay.setSpacing(12)
        for cell in cells:
            lbl = self._plain(QLabel(str(cell)))
            lbl.setWordWrap(True)
            if header:
                lbl.setStyleSheet(
                    f"color: {Color.SUBTEXT}; font-size: 11px; font-weight: 700;")
            else:
                lbl.setStyleSheet(f"color: {Color.TEXT}; font-size: 12px;")
            lay.addWidget(lbl, 1)
        if not header:
            row.setStyleSheet(
                f"background: {Color.SURFACE_0}; border-radius: {Radius.SM}px;")
        return row

    def _render_progress(self, element):
        from PySide6.QtWidgets import QProgressBar

        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        if element.text:
            caption = self._plain(QLabel(element.text))
            caption.setStyleSheet(f"color: {Color.SUBTEXT}; font-size: 12px;")
            lay.addWidget(caption)

        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(int(float(element.value or 0) * 100))
        bar.setTextVisible(False)
        bar.setFixedHeight(8)
        bar.setStyleSheet(f"""
            QProgressBar {{
                background: {Color.SURFACE_0};
                border: none; border-radius: 4px;
            }}
            QProgressBar::chunk {{
                background: {Color.ACCENT}; border-radius: 4px;
            }}
        """)
        lay.addWidget(bar)
        return box

    # ---------- действия ----------
    def _on_action(self, action, value=None):
        self._manager.dispatch_action(self._plugin_id, action, value)
        self.rebuild()      # состояние могло измениться — показываем актуальное
