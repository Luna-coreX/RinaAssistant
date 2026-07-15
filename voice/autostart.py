r"""
Автозапуск приложения при старте системы (кроссплатформенно).

Windows — ключ в реестре HKCU\...\Run.
Linux   — .desktop-файл в ~/.config/autostart.
macOS   — LaunchAgent plist в ~/Library/LaunchAgents.

Все операции обёрнуты в try/except и возвращают bool: успех/неуспех.
Команда запуска строится из текущего интерпретатора и main.py, чтобы
работать и при запуске из исходников, и (по возможности) из сборки.
"""

import os
import sys

APP_NAME = "RinaAssistant"


def _launch_command():
    """Команда, которая запускает приложение."""
    # если это «замороженная» сборка (PyInstaller и т.п.) — сам исполняемый файл
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    # иначе — интерпретатор + main.py проекта
    main_py = os.path.join(_project_root(), "main.py")
    return f'"{sys.executable}" "{main_py}"'


def _project_root():
    # ui/voice/autostart.py -> корень проекта на три уровня выше
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


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
    # для .desktop Exec без кавычек в стиле Windows
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
# Публичный интерфейс
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
    return True  # все три платформы поддержаны
