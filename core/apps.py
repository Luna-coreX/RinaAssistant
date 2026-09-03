# -*- coding: utf-8 -*-
"""
Какую программу человек имел в виду.

`4.0-G07`, решение — [ADR 0009](../docs/adr/0009-system-layer.md):
**индекс — данные операционной системы и живёт в оболочке; сопоставление —
язык и живёт здесь.** «Телеграм» → Telegram, «фотошоп» → Photoshop,
«вижуал студио» → который из двух (и надо переспросить) — это
транслитерация, нечёткое совпадение и разрешение неоднозначности, то есть
речь.

Довод, решивший развилку: позже сопоставление будет улучшать языковая
модель, а она живёт в ядре. Разложи мы это в оболочку — первое же
улучшение потребовало бы либо тащить модель туда, либо возвращать логику
обратно.

Модуль ничего не знает про Windows: ни реестра, ни меню «Пуск», ни `PATH`.
Ему дают список записей — откуда он взялся, его не касается. Поэтому
`find()` и требует `entries`: сходить и посмотреть самому ему нечем, и это
не недоделка, а граница.
"""

from voice.textmatch import has_cyrillic, normalize, similar, translit


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

    `entries` обязателен, хоть и со значением по умолчанию: сходить и
    посмотреть самому этому модулю нечем — индекс собирает оболочка
    (ADR 0009). Пустой список даёт пустой ответ, а не поход в систему.
    """
    variants = query_variants(query)
    if not variants or not entries:
        return []

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
