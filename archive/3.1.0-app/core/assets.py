"""
Access to the graphical assets (the logo, the icon).

Works both in development and in a built PyInstaller .exe (where the
resources lie in sys._MEIPASS). Pixmaps are cached by size, so as not to
recreate them on every repaint of the theme.
"""

import os
import sys

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtCore import Qt, QSize


def _base_dir() -> str:
    # In a built application the assets are unpacked into _MEIPASS
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return sys._MEIPASS
    # core/assets.py -> the project root one level up
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def asset_path(name: str) -> str:
    """The absolute path to a file inside assets/."""
    return os.path.join(_base_dir(), "assets", name)


_ICON_CACHE: dict[str, QIcon] = {}
_PIX_CACHE: dict[tuple, QPixmap] = {}
_SRC_CACHE: dict[str, QPixmap] = {}


def app_icon() -> QIcon:
    """The application's icon (window/tray/taskbar)."""
    if "app" not in _ICON_CACHE:
        path = asset_path("icon.ico")
        _ICON_CACHE["app"] = QIcon(path) if os.path.exists(path) else QIcon()
    return _ICON_CACHE["app"]


def _device_pixel_ratio() -> float:
    """The screen's scaling factor (for sharpness on HiDPI)."""
    app = QApplication.instance()
    if app is not None:
        screen = app.primaryScreen()
        if screen is not None:
            return screen.devicePixelRatio()
    return 1.0


def _emblem_source() -> QPixmap:
    """
    The logo's round emblem at high resolution (assets/emblem.png, 784x784,
    transparent background). This is the source for sharp scaling to any
    size.

    Fallback: if there is no emblem.png — we take the largest frame of
    icon.ico (256x256). Note: QPixmap('...ico') gives back the FIRST (16x16)
    frame, which is why the logo came out blurred — here we avoid that.
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
    The logo's emblem, sharply scaled to a square of `size` (logical px).

    We render from the large frame taking devicePixelRatio into account, so
    on HiDPI the picture stays sharp. The aspect is preserved — a square
    frame is not "squeezed".
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
