"""
Экспорт и импорт пользовательских данных.

Команды переносятся между компьютерами, история выгружается для чтения вне
приложения. Формат — JSON с версией и типом: без них импорт не отличит файл
команд от файла истории и не переживёт смену формата.

Импорт команд по умолчанию ДОБАВЛЯЕТ, а не заменяет: подменить весь набор
команд одним неверным кликом — слишком дорогая ошибка.
"""

import json
import time

from version import APP_VERSION


FORMAT_VERSION = 1
KIND_COMMANDS = "rina.commands"
KIND_HISTORY = "rina.history"


class TransferError(Exception):
    """Файл не подошёл: не тот формат, битый JSON, чужие данные."""


def _envelope(kind, payload):
    return {
        "kind": kind,
        "format": FORMAT_VERSION,
        "app_version": APP_VERSION,
        "exported_at": time.time(),
        "payload": payload,
    }


# ---------------------------------------------------------------------------
# Команды
# ---------------------------------------------------------------------------
def export_commands(path, commands, stats=None):
    """Сохраняет команды (и статистику запусков) в файл."""
    data = _envelope(KIND_COMMANDS, {
        "commands": list(commands or []),
        "stats": dict(stats or {}),
    })
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return len(data["payload"]["commands"])


def read_commands(path):
    """
    Читает файл команд. Возвращает список команд.
    Бросает TransferError, если файл не тот.
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        raise TransferError(f"Не удалось прочитать файл: {e}")

    if not isinstance(data, dict):
        raise TransferError("Файл не похож на экспорт Рины")

    # допускаем и «голый» список команд — его легко получить руками
    if "payload" not in data and isinstance(data.get("commands"), list):
        commands = data["commands"]
    else:
        if data.get("kind") != KIND_COMMANDS:
            raise TransferError("Это не файл команд")
        try:
            file_format = int(data.get("format", 0))
        except (TypeError, ValueError):
            raise TransferError("Не удалось прочитать версию формата файла")
        if file_format > FORMAT_VERSION:
            raise TransferError(
                "Файл сделан более новой версией Рины — обновите приложение")
        commands = (data.get("payload") or {}).get("commands", [])

    if not isinstance(commands, list):
        raise TransferError("В файле нет списка команд")
    if len(commands) > MAX_COMMANDS:
        raise TransferError(
            f"Слишком много команд в файле (больше {MAX_COMMANDS})")
    clean = [_sanitize_command(c) for c in commands
             if isinstance(c, dict) and c.get("triggers")]
    from core.logging_setup import security_log
    security_log().info(
        "Импорт команд из %s: в файле %d, принято %d, отброшено %d, "
        "все выключены", path, len(commands), len(clean),
        len(commands) - len(clean))
    return clean


# Файл команд мог быть написан кем угодно, а команда — это запуск программы.
# Поэтому импортированное приводится к безопасному виду и приходит выключенным:
# пользователь включает вручную, увидев, что именно он добавил.
MAX_COMMANDS = 500
MAX_TRIGGERS = 20
MAX_TRIGGER_LEN = 200
MIN_TRIGGER_LEN = 2


def _sanitize_command(raw):
    """Оставляет только известные поля и приводит их к ожидаемым типам."""
    from voice.user_commands import COMMAND_TYPES, SYSTEM_ACTIONS

    known_types = {t for t, _label, *_ in COMMAND_TYPES} | {"pause"}
    cmd_type = str(raw.get("type", "app"))
    if cmd_type not in known_types:
        cmd_type = "speak"          # неизвестный тип ничего не запускает

    triggers = []
    for trigger in (raw.get("triggers") or [])[:MAX_TRIGGERS]:
        trigger = str(trigger).strip()[:MAX_TRIGGER_LEN]
        # слишком короткая фраза срабатывала бы почти на любую реплику
        if len(trigger) >= MIN_TRIGGER_LEN:
            triggers.append(trigger)

    target = str(raw.get("target", ""))[:1000]
    if cmd_type == "system":
        actions = {a for a, _ in SYSTEM_ACTIONS}
        if target not in actions:
            cmd_type, target = "speak", ""

    steps = raw.get("steps") or []
    steps = [_sanitize_command(s) for s in steps[:50] if isinstance(s, dict)]

    return {
        "id": str(raw.get("id", "")),
        # импортированное всегда выключено: включение — осознанный шаг
        "enabled": False,
        "type": cmd_type,
        "triggers": triggers,
        "match": "exact" if raw.get("match") == "exact" else "contains",
        "target": target,
        "target_kind": "uwp" if raw.get("target_kind") == "uwp" else "file",
        "response": str(raw.get("response", ""))[:500],
        "steps": steps,
    }


def merge_commands(existing, incoming, new_id):
    """
    Досыпает импортированные команды к имеющимся.

    Совпадением считаем одинаковый набор фраз активации: id у файла с другого
    компьютера свой, а фразы — это то, чем команда является для пользователя.
    Возвращает (итоговый список, добавлено, пропущено дубликатов).
    """
    from voice.textmatch import normalize

    def key(cmd):
        return frozenset(normalize(t) for t in cmd.get("triggers", []) if t)

    result = list(existing or [])
    known = {key(c) for c in result}
    added = skipped = 0

    for cmd in incoming or []:
        cmd_key = key(cmd)
        if not cmd_key or cmd_key in known:
            skipped += 1
            continue
        copy = dict(cmd)
        copy["id"] = new_id()          # чужой id мог бы совпасть с местным
        result.append(copy)
        known.add(cmd_key)
        added += 1
    return result, added, skipped


# ---------------------------------------------------------------------------
# История
# ---------------------------------------------------------------------------
def export_history_json(path, entries):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(_envelope(KIND_HISTORY, {"history": list(entries or [])}),
                  f, ensure_ascii=False, indent=2)
    return len(entries or [])


def export_history_text(path, entries):
    """Читаемая выгрузка: дата, время, кто, текст."""
    lines = []
    last_day = None
    for entry in entries or []:
        stamp = time.localtime(entry.get("ts", 0))
        day = time.strftime("%d.%m.%Y", stamp)
        if day != last_day:
            lines.append("")
            lines.append(f"=== {day} ===")
            last_day = day
        who = "Вы" if entry.get("kind") == "user" else "Rina"
        lines.append(f"[{time.strftime('%H:%M', stamp)}] {who}: "
                     f"{entry.get('text', '')}")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines).strip() + "\n")
    return len(entries or [])
