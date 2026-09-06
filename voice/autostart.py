r"""
Starting the application when the system starts (cross-platform).

Windows — a key in the registry HKCU\...\Run.
Linux   — a .desktop file in ~/.config/autostart.
macOS   — a LaunchAgent plist in ~/Library/LaunchAgents.

Every operation is wrapped in try/except and returns a bool: success or
failure. The launch command is built from the current interpreter and
main.py, so as to work both when running from source and (where possible)
from a build.
"""

import os
import sys

APP_NAME = "RinaAssistant"


def _launch_command():
    """The command that launches the application."""
    # if this is a "frozen" build (PyInstaller and the like) — the executable itself
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    # otherwise — the interpreter plus the project's main.py
    main_py = os.path.join(_project_root(), "main.py")
    return f'"{sys.executable}" "{main_py}"'


def _project_root():
    # voice/autostart.py -> the project root two levels up
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ---------------------------------------------------------------------------
# Windows
# ---------------------------------------------------------------------------
def _win_enable():
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, _launch_command())
        winreg.CloseKey(key)
        return True
    except Exception:
        return False


def _win_disable():
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_SET_VALUE)
        try:
            winreg.DeleteValue(key, APP_NAME)
        except FileNotFoundError:
            pass
        winreg.CloseKey(key)
        return True
    except Exception:
        return False


def _win_is_enabled():
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_READ)
        try:
            winreg.QueryValueEx(key, APP_NAME)
            return True
        except FileNotFoundError:
            return False
        finally:
            winreg.CloseKey(key)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Linux
# ---------------------------------------------------------------------------
def _linux_path():
    d = os.path.join(os.path.expanduser("~"), ".config", "autostart")
    return os.path.join(d, f"{APP_NAME}.desktop")


def _linux_enable():
    try:
        path = _linux_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        content = (
            "[Desktop Entry]\n"
            "Type=Application\n"
            f"Name={APP_NAME}\n"
            f"Exec={_launch_command_plain()}\n"
            "X-GNOME-Autostart-enabled=true\n"
            "Terminal=false\n"
        )
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return True
    except Exception:
        return False


def _linux_disable():
    try:
        path = _linux_path()
        if os.path.isfile(path):
            os.remove(path)
        return True
    except Exception:
        return False


def _linux_is_enabled():
    return os.path.isfile(_linux_path())


def _launch_command_plain():
    # for a .desktop, Exec without quotes in the Windows style
    if getattr(sys, "frozen", False):
        return sys.executable
    return f'{sys.executable} {os.path.join(_project_root(), "main.py")}'


# ---------------------------------------------------------------------------
# macOS
# ---------------------------------------------------------------------------
def _mac_path():
    d = os.path.join(os.path.expanduser("~"), "Library", "LaunchAgents")
    return os.path.join(d, f"com.{APP_NAME.lower()}.plist")


def _mac_enable():
    try:
        path = _mac_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if getattr(sys, "frozen", False):
            args = f"<string>{sys.executable}</string>"
        else:
            args = (f"<string>{sys.executable}</string>"
                    f"<string>{os.path.join(_project_root(), 'main.py')}</string>")
        plist = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
            '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
            '<plist version="1.0"><dict>\n'
            f'<key>Label</key><string>com.{APP_NAME.lower()}</string>\n'
            f'<key>ProgramArguments</key><array>{args}</array>\n'
            '<key>RunAtLoad</key><true/>\n'
            '</dict></plist>\n'
        )
        with open(path, "w", encoding="utf-8") as f:
            f.write(plist)
        return True
    except Exception:
        return False


def _mac_disable():
    try:
        path = _mac_path()
        if os.path.isfile(path):
            os.remove(path)
        return True
    except Exception:
        return False


def _mac_is_enabled():
    return os.path.isfile(_mac_path())


# ---------------------------------------------------------------------------
# The public interface
# ---------------------------------------------------------------------------
def set_autostart(enabled: bool) -> bool:
    if sys.platform.startswith("win"):
        return _win_enable() if enabled else _win_disable()
    elif sys.platform == "darwin":
        return _mac_enable() if enabled else _mac_disable()
    else:
        return _linux_enable() if enabled else _linux_disable()


def is_autostart_enabled() -> bool:
    if sys.platform.startswith("win"):
        return _win_is_enabled()
    elif sys.platform == "darwin":
        return _mac_is_enabled()
    else:
        return _linux_is_enabled()


def supported() -> bool:
    return True  # all three platforms are supported
