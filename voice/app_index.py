"""
Индекс установленных приложений.

Раньше список запускаемых программ был захардкожен (пять штук в
voice/commands.py), и всё остальное приходилось добавлять руками. Здесь Рина
находит программы сама и запускает любую по имени.

Источники (Windows):
  * ярлыки меню «Пуск» — основной и самый «человеческий» источник: имена там
    уже такие, как их называет пользователь («Telegram», «Adobe Photoshop»);
  * приложения Магазина (UWP) — через `Get-StartApps`, запуск по AppUserModelID;
  * исполняемые файлы из PATH — как запасной слой для консольных утилит.

Ярлыки намеренно НЕ разбираются: `.lnk` запускается напрямую через
os.startfile(), поэтому не нужны ни pywin32, ни возня с разрешением целей.

Скан занимает секунды, поэтому результат кэшируется на диск и обновляется
в фоне (см. refresh_async).
"""

import json
import os
import subprocess
import sys
import threading
import time

from voice.textmatch import normalize, similar, translit, has_cyrillic


# Разговорные названия -> как программа называется в системе.
# Транслитерация вытягивает многое («блендер» -> blender), но не всё:
# «хром» -> hrom, «стим» -> stim, «ворд» -> vord — тут нужна прямая подсказка.
SPOKEN_ALIASES = {
    "хром": "chrome", "гугл хром": "chrome", "гуглхром": "chrome",
    "ворд": "word", "эксель": "excel", "поверпоинт": "powerpoint",
    "аутлук": "outlook", "оутлук": "outlook",
    "стим": "steam", "фотошоп": "photoshop", "фотошок": "photoshop",
    "телега": "telegram", "телеграмм": "telegram",
    "фаерфокс": "firefox", "файрфокс": "firefox", "фokc": "firefox",
    "опера": "opera", "яндекс": "yandex", "яндекс браузер": "yandex",
    "скайп": "skype", "зум": "zoom", "вайбер": "viber", "ватсап": "whatsapp",
    "спотифай": "spotify", "стимул": "steam",
    "обс": "obs", "вскод": "code", "вс код": "code", "вижуал студио": "visual studio",
    "питон": "python", "юнити": "unity", "анрил": "unreal",
    "премьер": "premiere", "иллюстратор": "illustrator", "автокад": "autocad",
    "майнкрафт": "minecraft", "эпик": "epic", "эпик геймс": "epic games",
    "проводник": "explorer",
    "клод": "claude", "клауд": "claude", "чатгпт": "chatgpt", "гпт": "chatgpt",
    "брейв": "brave", "эдж": "edge", "едж": "edge",
    "обсидиан": "obsidian", "стим": "steam",
    "терминал": "terminal", "командная строка": "cmd",
}

# Браузер — это не имя программы, а роль: у одного стоит Brave, у другого Edge.
# Ищем первый установленный из списка (порядок = приоритет).
BROWSER_WORDS = ("браузер", "browser", "интернет")
KNOWN_BROWSERS = ("chrome", "brave", "firefox", "edge", "opera", "yandex",
                  "vivaldi", "chromium")


CACHE_NAME = "app_index.json"
CACHE_TTL = 24 * 3600           # сутки: список программ меняется редко

# Ярлыки-мусор: в меню «Пуск» полно деинсталляторов, ридми и ссылок на сайты.
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

# Приоритет источников при дедупликации: чем меньше, тем важнее.
# Папки, указанные пользователем, идут высоко — он показал их осознанно.
SOURCE_ORDER = {"start_menu": 0, "desktop": 1, "folder": 2, "uwp": 3, "path": 4}

# Служебные подпапки: там лежат не программы, а их потроха
# (в Ren'Py SDK, например, lib/py3-windows-x86_64/python.exe).
SKIP_DIRS = {
    "lib", "libs", "library", "runtime", "resources", "res", "data",
    "plugins", "node_modules", "__pycache__", "vendor", "redist", "redistributable",
    "jre", "jdk", "python", "python3", "bin32", "x86", "update", "updates",
    "tmp", "temp", "cache", "logs", "log", "doc", "docs", "documentation",
    "samples", "examples", "sdk-fonts", "locale", "locales", "drivers",
}

# Служебные исполняемые: сопровождают программу, но запускать их не надо.
SKIP_EXE = {
    "python", "pythonw", "pip", "conda", "node", "zsync", "zsyncmake",
    "vcredist", "vc_redist", "dxsetup", "dotnetfx", "directx",
    "crashhandler", "crashpad_handler", "crashreporter", "bugreport",
    "updater", "update", "autoupdate", "setup", "install", "installer",
    "unins000", "uninstall", "uninstaller", "helper", "service", "daemon",
    "notification_helper", "elevate", "launcher_helper",
}

# Слишком общие имена: «game.exe» ничего не говорит — берём имя папки.
GENERIC_EXE = {"game", "start", "launcher", "run", "app", "main", "play",
               "program", "client", "engine"}

# Ограничители, чтобы скан пользовательских папок не превратился в обход диска
FOLDER_MAX_DEPTH = 3
FOLDER_MAX_ENTRIES = 400


class AppEntry:
    """Одно найденное приложение."""

    __slots__ = ("name", "launch", "kind", "source")

    def __init__(self, name, launch, kind, source):
        self.name = name        # отображаемое имя («Telegram Desktop»)
        self.launch = launch    # что запускать (путь к .lnk/.exe или AppID)
        self.kind = kind        # "file" | "uwp"
        self.source = source    # "start_menu" | "uwp" | "path"

    @property
    def key(self):
        return normalize(self.name)

    def to_dict(self):
        return {"name": self.name, "launch": self.launch,
                "kind": self.kind, "source": self.source}

    @classmethod
    def from_dict(cls, d):
        return cls(d.get("name", ""), d.get("launch", ""),
                   d.get("kind", "file"), d.get("source", "start_menu"))

    def __repr__(self):
        return f"<AppEntry {self.name!r} [{self.source}]>"


def _is_junk(name):
    low = name.lower()
    return any(word in low for word in SKIP_WORDS)


def _powershell():
    """Полный путь к PowerShell: по короткому имени Windows ищет и в текущей папке."""
    from voice.system_control import system_exe
    return system_exe("powershell.exe", os.path.join("System32",
                                                     "WindowsPowerShell", "v1.0"))


def _explorer():
    from voice.system_control import system_exe
    return system_exe("explorer.exe", "")


def _no_window():
    """Флаги, чтобы не мигало консольное окно при вызове PowerShell."""
    if sys.platform.startswith("win"):
        return {"creationflags": 0x08000000}   # CREATE_NO_WINDOW
    return {}


# ---------------------------------------------------------------------------
# Источники
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
    """Ярлыки меню «Пуск». Имя ярлыка = то, как программу зовёт пользователь."""
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
    Ярлыки рабочего стола. Portable-программы часто попадают в систему только
    так: в меню «Пуск» их нет, в реестре и PATH — тоже.
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
    Как называть найденную программу.

    Обычно имя файла и есть имя («renpy.exe» -> «renpy»), но у безымянных
    «game.exe» / «launcher.exe» смысл несёт папка — берём её.
    """
    stem = os.path.splitext(os.path.basename(exe_path))[0]
    if stem.lower() in GENERIC_EXE:
        parent = os.path.basename(os.path.dirname(exe_path))
        if parent:
            return parent
    return stem


def scan_program_folders(folders):
    """
    Сканирует указанные пользователем папки с portable-программами.

    Обходятся только «внешние» уровни: служебные подпапки (lib, runtime,
    resources…) пропускаются целиком — именно там лежат чужие python.exe
    и прочие потроха, которые запускать не нужно.
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
            # не спускаемся в служебные и скрытые каталоги
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
    """Приложения Магазина: имя + AppUserModelID через Get-StartApps."""
    if not sys.platform.startswith("win"):
        return []
    try:
        # PowerShell по умолчанию пишет в кодировке консоли (cp866 на русской
        # Windows) — русские имена («Блокнот», «Диспетчер задач») в UTF-8 читаются
        # как мусор. Просим сам PowerShell выдавать UTF-8.
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
        # обычные программы тоже попадают в Get-StartApps как путь к .exe —
        # их отдаём как файлы, а настоящие UWP запускаем через shell:AppsFolder
        if app_id.lower().endswith(".exe") and os.path.isabs(app_id):
            found.append(AppEntry(name, app_id, "file", "uwp"))
        else:
            found.append(AppEntry(name, app_id, "uwp", "uwp"))
    return found


def scan_path():
    """Исполняемые файлы из PATH — запасной слой (консольные утилиты)."""
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
# Сборка индекса
# ---------------------------------------------------------------------------
def program_folders():
    """Папки с portable-программами, указанные пользователем в настройках."""
    try:
        from core.settings_store import settings
        return list(settings.get("program_folders", []) or [])
    except Exception:
        return []


def build_index(include_path=True, folders=None):
    """Полный скан. Дубликаты схлопываются, приоритет — у меню «Пуск»."""
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
# Кэш
# ---------------------------------------------------------------------------
def _cache_path():
    from core.settings_store import config_dir
    return os.path.join(config_dir(), CACHE_NAME)


def load_cache():
    """(entries, timestamp) из кэша или ([], 0), если его нет/битый."""
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
    """Индекс из памяти/кэша; при необходимости — пересканирует."""
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
        else:                       # скан не дал результата — не теряем кэш
            _INDEX = _INDEX or load_cache()[0]
        return _INDEX


def cached_index():
    """
    Индекс без сканирования: только память или готовый кэш.

    get_index() при пустом кэше запускает полный обход (секунды, плюс запуск
    PowerShell) и держит блокировку — вызывать его из потока интерфейса нельзя,
    окно замирает. Страницы берут отсюда, а обновление просят в фоне.
    """
    if _INDEX is not None:
        return _INDEX
    cached, _ts = load_cache()
    return cached


def refresh_async(callback=None):
    """Пересканировать в фоне (скан занимает секунды — в GUI-потоке нельзя)."""
    def worker():
        entries = []
        try:
            entries = get_index(refresh=True)
        finally:
            # колбэк обязан сработать всегда: на нём разблокируется кнопка,
            # иначе она осталась бы серой с надписью «Ищу…» навсегда
            if callback:
                try:
                    callback(entries)
                except Exception:
                    pass
    threading.Thread(target=worker, daemon=True).start()


# ---------------------------------------------------------------------------
# Поиск и запуск
# ---------------------------------------------------------------------------
def query_variants(query):
    """
    Варианты написания запроса: как сказано, транслитом и по таблице
    разговорных названий. «фотошоп» ищется и как «fotoshop», и как «photoshop».
    """
    norm = normalize(query)
    if not norm:
        return []
    variants = [norm]
    alias = SPOKEN_ALIASES.get(norm)
    if alias:
        variants.append(normalize(alias))
    if has_cyrillic(norm):
        variants.append(translit(norm))
    # уникальные, непустые, в исходном порядке приоритета
    seen, result = set(), []
    for v in variants:
        if v and v not in seen:
            seen.add(v)
            result.append(v)
    return result


# Программы из PATH — это сотни служебных .exe (antiword, mobsync и т.п.).
# Их пускаем в выдачу только при уверенном совпадении, иначе они забивают
# нормальные приложения из меню «Пуск».
MIN_SCORE_PATH = 80


def _score(key, variant):
    if key == variant:
        return 100
    # совпадение с целым словом важнее совпадения с началом длинного слова:
    # «обс» -> «OBS Studio», а не «Obsidian»
    if variant in key.split():
        return 90
    if key.startswith(variant):
        return 80
    if variant in key:
        return 60
    if similar(key, variant):
        return 40
    return 0


def is_browser_query(query):
    """Просят «браузер» вообще, а не конкретную программу."""
    variants = query_variants(query)
    return bool(variants) and variants[0] in BROWSER_WORDS


def _find_browser(entries):
    """Установленные браузеры в порядке приоритета из KNOWN_BROWSERS."""
    result = []
    for wanted in KNOWN_BROWSERS:
        for entry in entries:
            words = entry.key.split()
            if wanted in words or entry.key.startswith(wanted):
                if entry not in result:
                    result.append(entry)
    return result


def find(query, limit=5, entries=None):
    """
    Кандидаты под запрос, от лучшего к худшему.

    Ранжирование: точное имя → начинается с запроса → содержит → похоже.
    Точность важнее полноты: запустить не ту программу неприятнее, чем
    переспросить.
    """
    variants = query_variants(query)
    if not variants:
        return []
    entries = entries if entries is not None else get_index()

    # «запусти браузер» — просят роль, а не конкретное имя
    if variants[0] in BROWSER_WORDS:
        found = _find_browser(entries)
        return found[:limit]

    scored = []
    for entry in entries:
        key = entry.key
        if not key:
            continue
        best = 0
        for i, variant in enumerate(variants):
            value = _score(key, variant)
            if value:
                # вариант «как сказано» чуть важнее производных
                value -= i
                best = max(best, value)
        if not best:
            continue
        if entry.source == "path" and best < MIN_SCORE_PATH:
            continue
        # более короткое имя при равном совпадении обычно и есть нужное
        scored.append((best, -len(key), entry))

    scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
    return [entry for _s, _l, entry in scored[:limit]]


def launch(entry):
    """Запускает приложение. True при успехе."""
    try:
        if entry.kind == "uwp":
            subprocess.Popen(
                [_explorer(), "shell:AppsFolder\\" + entry.launch],
                **_no_window())
            return True
        if sys.platform.startswith("win"):
            os.startfile(entry.launch)      # noqa: S606 — штатный запуск в ОС
        elif sys.platform == "darwin":
            subprocess.Popen(["open", entry.launch])
        else:
            subprocess.Popen([entry.launch])
        return True
    except Exception:
        return False
