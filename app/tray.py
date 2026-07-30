"""
Системный трей.

Иконка генерируется программно (рисуем кружок с акцентным цветом),
чтобы не тащить внешние ассеты. Меню: Открыть / Статус / Выход.
"""

from PySide6.QtWidgets import QSystemTrayIcon, QMenu, QApplication
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QBrush, QAction, QFont
from PySide6.QtCore import Qt, QObject, Signal

from core.i18n import t as tr
from core.theme import Color, theme_manager
from core.assets import app_icon


def make_tray_icon() -> QIcon:
    """Иконка трея — фирменная эмблема Rina (assets/icon.ico)."""
    icon = app_icon()
    if not icon.isNull():
        return icon

    # запасной вариант, если ассет недоступен: скруглённый квадрат + R
    size = 64
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QBrush(QColor(Color.ACCENT)))
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(4, 4, size - 8, size - 8, 16, 16)
    p.setPen(QColor("#ffffff"))
    f = QFont("Segoe UI", 30, QFont.Bold)
    p.setFont(f)
    p.drawText(pix.rect(), Qt.AlignCenter, "R")
    p.end()
    return QIcon(pix)


class SystemTray(QObject):
    show_requested = Signal()
    quit_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tray = QSystemTrayIcon(parent)
        self._tray.setIcon(make_tray_icon())
        self._tray.setToolTip("Rina Assistant")

        self._build_menu()
        self._tray.activated.connect(self._on_activated)

        # обновлять иконку при смене темы (меняется акцент)
        theme_manager.changed.connect(self._refresh_icon)

    def _build_menu(self):
        menu = QMenu()
        menu.setStyleSheet(f"""
            QMenu {{
                background: {Color.CRUST};
                color: {Color.TEXT};
                border: 1px solid {Color.SURFACE_1};
                border-radius: 8px;
                padding: 6px;
            }}
            QMenu::item {{
                padding: 8px 24px;
                border-radius: 6px;
            }}
            QMenu::item:selected {{
                background: {Color.ACCENT};
                color: #ffffff;
            }}
            QMenu::separator {{
                height: 1px;
                background: {Color.SURFACE_0};
                margin: 4px 8px;
            }}
        """)

        open_action = QAction(tr("Открыть Рину"), self)
        open_action.triggered.connect(self.show_requested.emit)
        menu.addAction(open_action)

        status_action = QAction("● Rina Online", self)
        status_action.setEnabled(False)
        menu.addAction(status_action)

        menu.addSeparator()

        quit_action = QAction(tr("Выход"), self)
        quit_action.triggered.connect(self.quit_requested.emit)
        menu.addAction(quit_action)

        self._menu = menu
        self._tray.setContextMenu(menu)

    def _on_activated(self, reason):
        # одиночный/двойной клик по иконке — показать окно
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.show_requested.emit()

    def _refresh_icon(self):
        self._tray.setIcon(make_tray_icon())
        self._build_menu()

    def notify(self, title, message, msecs=4000):
        """
        Показывает всплывающее уведомление у иконки трея.

        Возвращает True, если уведомление действительно отправлено. Важно:
        Qt молча игнорирует showMessage(), когда иконка трея скрыта (а она
        скрыта, если выключено «Сворачивать в трей»), поэтому вызывающий код
        должен уметь показать сообщение другим способом.
        """
        if not QSystemTrayIcon.supportsMessages():
            return False
        if not self._tray.isVisible():
            return False
        self._tray.showMessage(title, message, make_tray_icon(), msecs)
        return True

    def show(self):
        self._tray.show()

    def hide(self):
        self._tray.hide()

    def is_available(self):
        return QSystemTrayIcon.isSystemTrayAvailable()
