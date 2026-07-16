"""
Доступ к графическим ассетам (логотип, иконка).

Работает и в режиме разработки, и в собранном PyInstaller .exe
(там ресурсы лежат в sys._MEIPASS). Пиксмапы кэшируются по размеру,
чтобы не пересоздавать их на каждую перекраску темы.
"""

import os
import sys

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtCore import Qt, QSize


def _base_dir() -> str:
    # В собранном приложении ассеты распаковываются в _MEIPASS
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return sys._MEIPASS
    # core/assets.py -> корень проекта на уровень выше
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def asset_path(name: str) -> str:
    """Абсолютный путь к файлу внутри assets/."""
    return os.path.join(_base_dir(), "assets", name)


_ICON_CACHE: dict[str, QIcon] = {}
_PIX_CACHE: dict[tuple, QPixmap] = {}
_SRC_CACHE: dict[str, QPixmap] = {}


def app_icon() -> QIcon:
    """Иконка приложения (окно/трей/панель задач)."""
    if "app" not in _ICON_CACHE:
        path = asset_path("icon.ico")
        _ICON_CACHE["app"] = QIcon(path) if os.path.exists(path) else QIcon()
    return _ICON_CACHE["app"]


def _device_pixel_ratio() -> float:
    """Коэффициент масштабирования экрана (для чёткости на HiDPI)."""
    app = QApplication.instance()
    if app is not None:
        screen = app.primaryScreen()
        if screen is not None:
            return screen.devicePixelRatio()
    return 1.0


def _emblem_source() -> QPixmap:
    """
    Высокого разрешения круглая эмблема логотипа (assets/emblem.png, 784×784,
    прозрачный фон). Это источник для чёткого масштабирования в любой размер.

    Fallback: если emblem.png нет — берём самый крупный кадр icon.ico (256×256).
    Важно: QPixmap('...ico') отдаёт ПЕРВЫЙ (16×16) кадр, поэтому логотип
    получался размытым — здесь мы этого избегаем.
    """
    if "emblem" not in _SRC_CACHE:
        path = asset_path("emblem.png")
        if os.path.exists(path):
            _SRC_CACHE["emblem"] = QPixmap(path)
        else:
            _SRC_CACHE["emblem"] = app_icon().pixmap(QSize(256, 256))
    return _SRC_CACHE["emblem"]


def logo_pixmap(size: int) -> QPixmap:
    """
    Эмблема логотипа, чётко отмасштабированная до квадрата `size` (лог. px).

    Рендерим из крупного кадра с учётом devicePixelRatio, поэтому на HiDPI
    картинка остаётся резкой. Аспект сохраняется — квадратный кадр не «сжимается».
    """
    dpr = _device_pixel_ratio()
    key = ("emblem", size, round(dpr * 100))
    if key not in _PIX_CACHE:
        src = _emblem_source()
        if src.isNull():
            _PIX_CACHE[key] = src
        else:
            px = max(1, round(size * dpr))
            pm = src.scaled(px, px, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            pm.setDevicePixelRatio(dpr)
            _PIX_CACHE[key] = pm
    return _PIX_CACHE[key]
