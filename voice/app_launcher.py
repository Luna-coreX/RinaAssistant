"""
Запуск программ по имени: «запусти телеграм», «открой блокнот».

Раньше список был захардкожен (пять программ), теперь имя ищется в индексе
установленных приложений (voice/app_index.py). Если подходящих несколько —
не гадаем, а возвращаем список кандидатов, чтобы ассистент переспросил:
запустить не ту программу неприятнее, чем задать уточняющий вопрос.
"""

import os
import re

from core.i18n import t as tr
from voice import app_index
from voice.textmatch import normalize


LAUNCH_VERBS = (
    "запусти", "запустить", "открой", "открыть", "включи", "включить",
    "стартани", "launch", "open", "start", "run",
)

# Слова-паразиты после глагола: «запусти мне программу телеграм»
FILLER_WORDS = (
    "мне", "пожалуйста", "программу", "приложение", "прогу", "плиз",
    "давай", "please", "the", "app", "application",
)

# Насколько кандидаты должны отличаться, чтобы выбрать первого без вопроса
DECISIVE_GAP = 10


class LaunchOutcome:
    """Результат попытки запуска: что сказать и нужен ли уточняющий вопрос."""

    def __init__(self, status, message, options=None, query=""):
        self.status = status          # "launched" | "ambiguous" | "not_found"
        self.message = message
        self.options = options or []
        self.query = query            # что искали (нужно для «запомни путь»)


# ---------------------------------------------------------------------------
# Запомненные пользователем программы
# ---------------------------------------------------------------------------
def _aliases():
    from core.settings_store import settings
    return dict(settings.get("app_aliases", {}) or {})


def remember(query, path, kind="file", name=None):
    """
    Запомнить, что «ренпай» — это вот эта программа.

    Хранится словарём, потому что запомнить нужно не только путь: у приложений
    Магазина вместо файла AppUserModelID, и проверять его существование на
    диске бессмысленно.
    """
    from core.settings_store import settings
    key = normalize(query)
    if not key or not path:
        return False
    aliases = _aliases()
    aliases[key] = {
        "path": path,
        "kind": kind,
        "name": name or os.path.splitext(os.path.basename(path))[0],
    }
    settings.set("app_aliases", aliases)
    settings.save()
    return True


def forget(query):
    from core.settings_store import settings
    aliases = _aliases()
    if aliases.pop(normalize(query), None) is None:
        return False
    settings.set("app_aliases", aliases)
    settings.save()
    return True


def alias_entry(target):
    """Запомненная программа под этот запрос (или None)."""
    saved = _aliases().get(normalize(target))
    if not saved:
        return None

    # старый формат — просто строка с путём
    if isinstance(saved, str):
        saved = {"path": saved, "kind": "file",
                 "name": os.path.splitext(os.path.basename(saved))[0]}

    path = saved.get("path")
    if not path:
        return None
    kind = saved.get("kind", "file")
    # у приложений Магазина вместо пути идентификатор — проверять нечего
    if kind == "file" and not os.path.exists(path):
        forget(target)          # путь устарел — не держим мусор
        return None
    name = saved.get("name") or os.path.splitext(os.path.basename(path))[0]
    return app_index.AppEntry(name, path, kind, "learned")


def extract_target(text):
    """
    Возвращает имя программы после глагола запуска или None,
    если фраза вообще не про запуск.
    """
    if not text:
        return None
    low = normalize(text)
    if not low:
        return None

    words = low.split()
    verb_at = None
    for i, word in enumerate(words):
        if word in LAUNCH_VERBS:
            verb_at = i
            break
    if verb_at is None:
        return None

    rest = [w for w in words[verb_at + 1:] if w not in FILLER_WORDS]
    target = " ".join(rest).strip()
    return target or None


def _fallback_catalog(target):
    """
    Запасной каталог для систем, где индекс пуст (не Windows).
    Использует прежний захардкоженный список из voice/commands.py.
    """
    try:
        from voice.commands import APPS, _launch
    except Exception:
        return None
    for key, app in APPS.items():
        if any(name in target for name in app["names"]):
            if _launch(key):
                return tr("Хорошо, запускаю {app}.", app=tr(app["label"]))
            return tr("Не получилось запустить {app} — возможно, "
                      "приложение не установлено.", app=tr(app["label"]))
    return None


def resolve(text):
    """
    Обрабатывает команду запуска.
    Возвращает LaunchOutcome или None, если фраза не про запуск программы.
    """
    target = extract_target(text)
    if not target:
        return None

    # то, что пользователь показал вручную, важнее результатов поиска
    learned = alias_entry(target)
    if learned is not None:
        if app_index.launch(learned):
            return LaunchOutcome(
                "launched", tr("Запускаю {app}.", app=learned.name))
        return LaunchOutcome(
            "not_found",
            tr("Не получилось запустить {app} — программу удалили "
               "или перенесли.", app=learned.name),
            query=target)

    candidates = app_index.find(target, limit=5)

    if not candidates:
        message = _fallback_catalog(target)
        if message:
            return LaunchOutcome("launched", message)
        return LaunchOutcome(
            "not_found",
            tr("Не нашла программу «{name}».", name=target),
            query=target)

    # один кандидат или явный лидер — запускаем без вопросов.
    # «запусти браузер» тоже не переспрашиваем: просят роль, а не конкретную
    # программу — берём первый по приоритету, как это делает система.
    decisive = len(candidates) == 1 or app_index.is_browser_query(target)
    if not decisive:
        top = app_index.find(target, limit=2)
        if len(top) >= 2:
            scores = [_candidate_score(target, e) for e in top[:2]]
            decisive = (scores[0] - scores[1]) >= DECISIVE_GAP

    if decisive:
        entry = candidates[0]
        if app_index.launch(entry):
            return LaunchOutcome(
                "launched", tr("Запускаю {app}.", app=entry.name))
        return LaunchOutcome(
            "not_found",
            tr("Не получилось запустить {app} — программу удалили "
               "или перенесли.", app=entry.name))

    names = ", ".join(e.name for e in candidates[:3])
    return LaunchOutcome(
        "ambiguous",
        tr("Нашла несколько: {names}. Какое запустить?", names=names),
        options=candidates[:3], query=target)


def _candidate_score(target, entry):
    """Оценка кандидата тем же способом, что и в индексе (для сравнения пары)."""
    best = 0
    for variant in app_index.query_variants(target):
        best = max(best, app_index._score(entry.key, variant))
    return best


# ---------------------------------------------------------------------------
# Ответ на уточняющий вопрос
# ---------------------------------------------------------------------------
ORDINALS = {
    "первый": 0, "первое": 0, "первая": 0, "первую": 0, "1": 0, "один": 0,
    "второй": 1, "второе": 1, "вторая": 1, "вторую": 1, "2": 1, "два": 1,
    "третий": 2, "третье": 2, "третья": 2, "третью": 2, "3": 2, "три": 2,
    "first": 0, "second": 1, "third": 2,
}

CANCEL_WORDS = ("отмена", "отмени", "неважно", "ничего", "забудь", "никакое",
                "cancel", "never mind", "nothing")


def choose(text, options):
    """
    Выбирает вариант из предложенных по ответу пользователя.
    Возвращает (entry | None, cancelled: bool).
    """
    low = normalize(text)
    if not low:
        return None, False
    if any(word in low for word in CANCEL_WORDS):
        return None, True

    # «второй», «два», «2»
    for word in low.split():
        if word in ORDINALS:
            idx = ORDINALS[word]
            if idx < len(options):
                return options[idx], False

    # «obs studio» — по имени
    ranked = app_index.find(low, limit=1, entries=options)
    if ranked:
        return ranked[0], False
    return None, False
