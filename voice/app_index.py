"""
The index of installed applications.

The list of launchable programs used to be hard-coded (five of them in
voice/commands.py), and everything else had to be added by hand. Here Rina
finds programs herself and launches any of them by name.

The sources (Windows):
  * Start-menu shortcuts — the main and most "human" source: the names there
    are already what the user calls them ("Telegram", "Adobe Photoshop");
  * Store (UWP) applications — through `Get-StartApps`, launched by
    AppUserModelID;
  * executables from PATH — a fallback layer for console utilities.

The shortcuts are deliberately NOT parsed: a `.lnk` is launched directly
through os.startfile(), so neither pywin32 nor fiddling with resolving
targets is needed.

A scan takes seconds, so the result is cached to disk and refreshed in the
background (see refresh_async).
"""

import json
import os
import subprocess
import sys
import threading
import time

from voice.textmatch import normalize, similar, translit, has_cyrillic

# Name matching moved into the core (4.0-G07, ADR 0009). Here it is
# **reused** rather than repeated: two copies of the dictionary of spoken
# names would part company at the first change. This module stayed for the
# sake of the 3.1.0 application — it lives in one process and has no shell.
from core.apps import (AppEntry, BROWSER_WORDS, KNOWN_BROWSERS,
                       MIN_SCORE_PATH, SPOKEN_ALIASES, _find_browser, _score,
                       find as match, is_browser_query, query_variants)
from core.logging_setup import get_logger


log = get_logger("apps")


def find(query, limit=5, entries=None):
    """The core's matching over the index assembled here."""
    return match(query, limit=limit,
                 entries=entries if entries is not None else get_index())


BROWSER_WORDS = ("браузер", "browser", "интернет")
KNOWN_BROWSERS = ("chrome", "brave", "firefox", "edge", "opera", "yandex",
                  "vivaldi", "chromium")


CACHE_NAME = "app_index.json"
CACHE_TTL = 24 * 3600           # a day: the list of programs changes rarely

# Junk shortcuts: the Start menu is full of uninstallers, readmes and links to sites.
SKIP_WORDS = (
    "uninstall", "деинсталл", "удалить", "удаление",
    "readme", "read me", "прочти", "лицензи", "license", "licence",
    "help", "справка", "документаци", "documentation", "manual",
    "release notes", "changelog", "что нового",
    "website", "веб-сайт", "домашняя страница", "home page",
    "report a bug", "сообщить об ошибке", "поддержка", "support",
    "модифицировать", "modify", "repair", "восстановление",
    "командная строка разработчика", "developer command prompt",
)

# The priority of sources when de-duplicating: the smaller, the more
# important. Folders named by the user rank high — they pointed at them
# deliberately.
SOURCE_ORDER = {"start_menu": 0, "desktop": 1, "folder": 2, "uwp": 3, "path": 4}

# Internal subfolders: what lies there is not programs but their innards
# (in the Ren'Py SDK, for instance, lib/py3-windows-x86_64/python.exe).
SKIP_DIRS = {
    "lib", "libs", "library", "runtime", "resources", "res", "data",
    "plugins", "node_modules", "__pycache__", "vendor", "redist", "redistributable",
    "jre", "jdk", "python", "python3", "bin32", "x86", "update", "updates",
    "tmp", "temp", "cache", "logs", "log", "doc", "docs", "documentation",
    "samples", "examples", "sdk-fonts", "locale", "locales", "drivers",
}

# Internal executables: they accompany a program, but must not be launched.
SKIP_EXE = {
    "python", "pythonw", "pip", "conda", "node", "zsync", "zsyncmake",
    "vcredist", "vc_redist", "dxsetup", "dotnetfx", "directx",
    "crashhandler", "crashpad_handler", "crashreporter", "bugreport",
    "updater", "update", "autoupdate", "setup", "install", "installer",
    "unins000", "uninstall", "uninstaller", "helper", "service", "daemon",
    "notification_helper", "elevate", "launcher_helper",
}

# Names that are too general: "game.exe" says nothing — we take the folder's name.
GENERIC_EXE = {"game", "start", "launcher", "run", "app", "main", "play",
               "program", "client", "engine"}

# Limits, so that scanning the user's folders does not turn into a walk of the disk
FOLDER_MAX_DEPTH = 3
FOLDER_MAX_ENTRIES = 400


def _is_junk(name):
    low = name.lower()
    return any(word in low for word in SKIP_WORDS)


def _powershell():
    """The full path to PowerShell: by a short name Windows also looks in the current folder."""
    from voice.system_control import system_exe
    return system_exe("powershell.exe", os.path.join("System32",
                                                     "WindowsPowerShell", "v1.0"))


def _explorer():
    from voice.system_control import system_exe
    return system_exe("explorer.exe", "")


def _no_window():
    """Flags, so that a console window does not flash when PowerShell is called."""
    if sys.platform.startswith("win"):
        return {"creationflags": 0x08000000}   # CREATE_NO_WINDOW
    return {}


# ---------------------------------------------------------------------------
# The sources
# ---------------------------------------------------------------------------
def _start_menu_dirs():
    dirs = []
    for env in ("ProgramData", "APPDATA"):
        base = os.environ.get(env)
        if base:
            path = os.path.join(base, "Microsoft", "Windows",
                                "Start Menu", "Programs")
            if os.path.isdir(path):
                dirs.append(path)
    return dirs


def scan_start_menu():
    """Start-menu shortcuts. A shortcut's name = what the user calls the program."""
    found = []
    for base in _start_menu_dirs():
        for root, _dirs, files in os.walk(base):
            for fname in files:
                stem, ext = os.path.splitext(fname)
                if ext.lower() not in (".lnk", ".appref-ms"):
                    continue
                if _is_junk(stem):
                    continue
                found.append(AppEntry(stem, os.path.join(root, fname),
                                      "file", "start_menu"))
    return found


def _desktop_dirs():
    dirs = []
    for env in ("USERPROFILE", "PUBLIC", "OneDrive"):
        base = os.environ.get(env)
        if base:
            path = os.path.join(base, "Desktop")
            if os.path.isdir(path):
                dirs.append(path)
    return dirs


def scan_desktop():
    """
    Desktop shortcuts. Portable programs often get into the system only this
    way: they are not in the Start menu, nor in the registry, nor in PATH.
    """
    found, seen = [], set()
    for base in _desktop_dirs():
        try:
            names = os.listdir(base)
        except OSError:
            continue
        for fname in names:
            stem, ext = os.path.splitext(fname)
            if ext.lower() not in (".lnk", ".url", ".appref-ms"):
                continue
            if _is_junk(stem) or stem.lower() in seen:
                continue
            seen.add(stem.lower())
            found.append(AppEntry(stem, os.path.join(base, fname),
                                  "file", "desktop"))
    return found


def _exe_display_name(exe_path):
    """
    What to call a program that was found.

    Usually the file's name is the name ("renpy.exe" -> "renpy"), but for
    nameless "game.exe" / "launcher.exe" the meaning is carried by the
    folder — we take that.
    """
    stem = os.path.splitext(os.path.basename(exe_path))[0]
    if stem.lower() in GENERIC_EXE:
        parent = os.path.basename(os.path.dirname(exe_path))
        if parent:
            return parent
    return stem


def scan_program_folders(folders):
    """
    Scans the folders of portable programs named by the user.

    Only the "outer" levels are walked: internal subfolders (lib, runtime,
    resources...) are skipped whole — it is precisely there that other
    people's python.exe and similar innards lie, which must not be launched.
    """
    found = []
    for root_folder in folders or []:
        root_folder = str(root_folder).strip()
        if not root_folder or not os.path.isdir(root_folder):
            continue
        base_depth = root_folder.rstrip("\\/").count(os.sep)
        count = 0
        for root, dirs, files in os.walk(root_folder):
            depth = root.rstrip("\\/").count(os.sep) - base_depth
            if depth >= FOLDER_MAX_DEPTH:
                dirs[:] = []
            # we do not descend into internal and hidden directories
            dirs[:] = [d for d in dirs
                       if d.lower() not in SKIP_DIRS and not d.startswith(".")]
            for fname in files:
                stem, ext = os.path.splitext(fname)
                if ext.lower() != ".exe":
                    continue
                if stem.lower() in SKIP_EXE or _is_junk(stem):
                    continue
                name = _exe_display_name(os.path.join(root, fname))
                found.append(AppEntry(name, os.path.join(root, fname),
                                      "file", "folder"))
                count += 1
                if count >= FOLDER_MAX_ENTRIES:
                    break
            if count >= FOLDER_MAX_ENTRIES:
                break
    return found


def scan_uwp():
    """Store applications: the name plus the AppUserModelID, through Get-StartApps."""
    if not sys.platform.startswith("win"):
        return []
    try:
        # By default PowerShell writes in the console's encoding (cp866 on a
        # Russian Windows) — Russian names ("Блокнот", "Диспетчер задач") are
        # read as rubbish in UTF-8. We ask PowerShell itself to give out
        # UTF-8.
        proc = subprocess.run(
            [_powershell(), "-NoProfile", "-NonInteractive", "-Command",
             "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; "
             "Get-StartApps | ConvertTo-Json -Compress"],
            capture_output=True, timeout=25, **_no_window())
        raw = proc.stdout.decode("utf-8", errors="replace").strip()
        if not raw:
            return []
        data = json.loads(raw)
    except Exception:
        return []

    if isinstance(data, dict):
        data = [data]
    found = []
    for item in data or []:
        name = (item.get("Name") or "").strip()
        app_id = (item.get("AppID") or "").strip()
        if not name or not app_id or _is_junk(name):
            continue
        # ordinary programs also land in Get-StartApps as a path to an .exe
        # — we hand those over as files, and launch real UWP ones through
        # shell:AppsFolder
        if app_id.lower().endswith(".exe") and os.path.isabs(app_id):
            found.append(AppEntry(name, app_id, "file", "uwp"))
        else:
            found.append(AppEntry(name, app_id, "uwp", "uwp"))
    return found


def scan_path():
    """Executables from PATH — a fallback layer (console utilities)."""
    found, seen = [], set()
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        directory = directory.strip('"')
        if not directory or not os.path.isdir(directory):
            continue
        try:
            names = os.listdir(directory)
        except OSError:
            continue
        for fname in names:
            stem, ext = os.path.splitext(fname)
            if ext.lower() not in (".exe", ".bat", ".cmd"):
                continue
            low = stem.lower()
            if low in seen or _is_junk(stem):
                continue
            full = os.path.join(directory, fname)
            if os.path.isfile(full):
                seen.add(low)
                found.append(AppEntry(stem, full, "file", "path"))
    return found


# ---------------------------------------------------------------------------
# Assembling the index
# ---------------------------------------------------------------------------
def program_folders():
    """Folders of portable programs named by the user in the settings."""
    try:
        from core.settings_store import settings
        return list(settings.get("program_folders", []) or [])
    except Exception:
        return []


def build_index(include_path=True, folders=None):
    """A full scan. Duplicates collapse; the Start menu has priority."""
    if folders is None:
        folders = program_folders()
    entries = (scan_start_menu() + scan_desktop()
               + scan_program_folders(folders) + scan_uwp())
    if include_path:
        entries += scan_path()

    best = {}
    for entry in entries:
        key = entry.key
        if not key:
            continue
        current = best.get(key)
        if current is None or (SOURCE_ORDER.get(entry.source, 9)
                               < SOURCE_ORDER.get(current.source, 9)):
            best[key] = entry
    return sorted(best.values(), key=lambda e: e.name.lower())


# ---------------------------------------------------------------------------
# The cache
# ---------------------------------------------------------------------------
def _cache_path():
    from core.settings_store import config_dir
    return os.path.join(config_dir(), CACHE_NAME)


def load_cache():
    """(entries, timestamp) from the cache, or ([], 0) if there is none or it is broken."""
    try:
        with open(_cache_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
        entries = [AppEntry.from_dict(d) for d in data.get("apps", [])]
        return entries, float(data.get("ts", 0))
    except (OSError, ValueError, TypeError):
        return [], 0.0


def save_cache(entries):
    payload = {"ts": time.time(), "apps": [e.to_dict() for e in entries]}
    try:
        with open(_cache_path(), "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
        return True
    except OSError:
        return False


_INDEX = None
_LOCK = threading.Lock()


def get_index(refresh=False):
    """The index from memory or the cache; rescans if need be."""
    global _INDEX
    with _LOCK:
        if _INDEX is not None and not refresh:
            return _INDEX
        if not refresh:
            cached, ts = load_cache()
            if cached and (time.time() - ts) < CACHE_TTL:
                _INDEX = cached
                return _INDEX
        entries = build_index()
        if entries:
            _INDEX = entries
            save_cache(entries)
        else:                       # the scan gave nothing — we do not lose the cache
            _INDEX = _INDEX or load_cache()[0]
        return _INDEX


def cached_index():
    """
    The index without scanning: memory or a ready cache only.

    With an empty cache, get_index() starts a full walk (seconds, plus
    starting PowerShell) and holds a lock — it must not be called from the
    interface thread, or the window freezes. The pages take from here, and
    ask for a refresh in the background.
    """
    if _INDEX is not None:
        return _INDEX
    cached, _ts = load_cache()
    return cached


def refresh_async(callback=None):
    """Rescan in the background (the scan takes seconds — not in the GUI thread)."""
    def worker():
        entries = []
        try:
            entries = get_index(refresh=True)
        finally:
            # the callback is obliged to fire in any case: it is what
            # unblocks the button, or it would stay grey saying "Searching…"
            # forever
            if callback:
                try:
                    callback(entries)
                except Exception:
                    pass
    threading.Thread(target=worker, daemon=True).start()


# ---------------------------------------------------------------------------
# Searching and launching
# ---------------------------------------------------------------------------
def _uwp_known(app_id):
    """
    Is there such an AppUserModelID among the Store applications found.

    There is no other way to check: explorer.exe finishes at once and
    reports nothing about the fate of `shell:AppsFolder\\<id>`, and it must
    not be waited for — if the file manager is not running yet, it becomes
    the shell and does not finish at all. So we compare with the index
    before launching.
    """
    index = cached_index()
    if not index:
        return True         # no index, nothing to judge by: we try to launch
    return any(e.kind == "uwp" and e.launch == app_id for e in index)


def launch(entry):
    """Launches the application. True on success."""
    try:
        if entry.kind == "uwp":
            if not _uwp_known(entry.launch):
                log.warning("Приложение Магазина не найдено: %s", entry.launch)
                return False
            subprocess.Popen(
                [_explorer(), "shell:AppsFolder\\" + entry.launch],
                **_no_window())
            return True

        # The index lives for a day, and the program may have been deleted
        # in that time. Handing the system a non-existent path in silence
        # means showing the user a system error instead of an intelligible
        # answer.
        if os.path.isabs(entry.launch) and not os.path.exists(entry.launch):
            log.warning("Путь не существует: %s", entry.launch)
            return False

        if sys.platform.startswith("win"):
            os.startfile(entry.launch)      # noqa: S606 — the OS's normal launch
        elif sys.platform == "darwin":
            subprocess.Popen(["open", entry.launch])
        else:
            subprocess.Popen([entry.launch])
        return True
    except Exception:
        log.exception("Не удалось запустить %s", entry.name)
        return False
