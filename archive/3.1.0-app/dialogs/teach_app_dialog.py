"""
Окно «покажи, что запускать».

Появляется, когда Рина не нашла программу: portable-версии и распакованные
папкой программы негде искать — у них нет ни ярлыка в «Пуске», ни записи в
реестре. Пользователь один раз указывает файл, дальше Рина запускает сама.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFileDialog
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from core.i18n import t as tr
from core.theme import Color, FONT_FAMILY, Radius


class TeachAppDialog(QDialog):
    def __init__(self, query, parent=None):
        super().__init__(parent)
        self._query = query
        self._path = None
        self.setWindowTitle(tr("Программа не найдена"))
        self.setModal(False)
        self.setMinimumWidth(430)
        self.setStyleSheet(f"QDialog {{ background: {Color.BASE}; }}")
        self._build()

    def chosen_path(self):
        return self._path

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 24, 26, 22)
        layout.setSpacing(12)

        title = QLabel(tr("Не нашла «{name}»", name=self._query))
        title.setFont(QFont(FONT_FAMILY, 16, QFont.Bold))
        title.setStyleSheet(f"color: {Color.TEXT};")
        title.setWordWrap(True)
        layout.addWidget(title)

        desc = QLabel(tr(
            "Похоже, программа не установлена обычным способом. Укажите файл — "
            "я запомню и в следующий раз запущу сама."))
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {Color.SUBTEXT}; font-size: 13px;")
        layout.addWidget(desc)

        btns = QHBoxLayout()
        btns.addStretch()

        cancel = QPushButton(tr("Не нужно"))
        cancel.setCursor(Qt.PointingHandCursor)
        cancel.setFixedHeight(38)
        cancel.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {Color.SUBTEXT};
                border: 1px solid {Color.SURFACE_1}; border-radius: {Radius.SM}px;
                padding: 4px 20px; font-size: 13px;
            }}
            QPushButton:hover {{ background: {Color.SURFACE_0}; }}
        """)
        cancel.clicked.connect(self.reject)

        pick = QPushButton(tr("Указать файл…"))
        pick.setCursor(Qt.PointingHandCursor)
        pick.setFixedHeight(38)
        pick.setStyleSheet(f"""
            QPushButton {{
                background: {Color.ACCENT}; color: #ffffff;
                border: none; border-radius: {Radius.SM}px;
                padding: 4px 22px; font-size: 13px; font-weight: 600;
            }}
            QPushButton:hover {{ background: {Color.alpha(Color.ACCENT, 'dd')}; }}
        """)
        pick.clicked.connect(self._pick_file)

        btns.addWidget(cancel)
        btns.addWidget(pick)
        layout.addLayout(btns)

    def _pick_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, tr("Файл программы"), "",
            tr("Программы (*.exe *.lnk *.bat *.cmd);;Все файлы (*)"))
        if path:
            self._path = path
            self.accept()
