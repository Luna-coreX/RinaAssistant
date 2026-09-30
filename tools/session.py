"""
Запись и воспроизведение сессий (задача плана 4.0-A05).

Golden-набор проверяет фразы. Есть вещи, которых он не ловит по устройству:

    * незакрытый вопрос, протухший по времени;
    * подтверждение, снятое посторонней репликой;
    * цепочку, где состояние копится через несколько шагов.

Здесь записывается **последовательность** — ввод, решение, ответ и побочные
эффекты вместе с промежутками между шагами, — и воспроизводится с тем же
временем. Промежуток записан явно, поэтому воспроизведение не ждёт минуту
по-настоящему: часы подменяются.

Записанная сессия — это данные. После переноса ядра на C# тот же файл будет
воспроизводиться против ядра-сервиса, как и golden-набор.

Запуск:
    python tools/session.py --list
    python tools/session.py --replay docs/golden/sessions/confirm-expired.json
    python tools/session.py --replay-all
"""

import argparse
import glob
import json
import os
import re
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

SESSIONS_DIR = os.path.join(ROOT, "docs", "golden", "sessions")


# ---------------------------------------------------------------------------
# Приведение к сравнимому виду
# ---------------------------------------------------------------------------
#: Что в ответе зависит от момента запуска, а не от поведения.
_VOLATILE = (
    # Время по часам: «02:15».
    (re.compile(r"\b\d{1,2}:\d{2}\b"), "ЧЧ:ММ"),
    # Обратный отсчёт: «9 мин 59 с» — зависит от доли секунды.
    (re.compile(r"\b\d+ мин \d+ с\b"), "N мин N с"),
    (re.compile(r"\b\d+ с\b"), "N с"),
)


def normalise(text):
    """
    Убирает из ответа то, что меняется от прогона к прогону.

    Сессия проверяет поведение: что Рина сказала и сделала. Показания часов
    и остаток до срабатывания при воспроизведении будут другими всегда, и
    сравнивать их — значит получить вечно красный тест.
    """
    if not text:
        return text
    for pattern, placeholder in _VOLATILE:
        text = pattern.sub(placeholder, text)
    return text


def normalise_effects(effects):
    """Отметки времени в побочных эффектах — тоже не поведение."""
    clean = {}
    for name, items in (effects or {}).items():
        if name == "reminders":
            clean[name] = [{k: v for k, v in item.items() if k != "fire_at"}
                           for item in items]
        else:
            clean[name] = list(items)
    return clean


# ---------------------------------------------------------------------------
# Подменные часы
# ---------------------------------------------------------------------------
class FakeClock:
    """
    Управляемое время для проверки сроков.

    Подменяет часы там, где ядро смотрит на срок вопроса. Без этого проверка
    протухания стоила бы минуты ожидания на каждый прогон — то есть её бы
    просто не было.
    """

    def __init__(self, start=None):
        self.now = start if start is not None else time.time()
        self._patched = []

    def advance(self, seconds):
        self.now += float(seconds or 0)

    def install(self):
        from core import dialog

        self._patched.append((dialog.time, "time", dialog.time.time))
        dialog.time = _ClockModule(self)
        return self

    def uninstall(self):
        from core import dialog
        import time as real_time

        dialog.time = real_time
        self._patched.clear()


class _ClockModule:
    """Заменитель модуля time с управляемым time()."""

    def __init__(self, clock):
        self._clock = clock

    def time(self):
        return self._clock.now

    def __getattr__(self, name):
        import time as real_time

        return getattr(real_time, name)


# ---------------------------------------------------------------------------
# Запись
# ---------------------------------------------------------------------------
class SessionRecorder:
    """
    Пишет всё, что проходит через ядро.

    Прикрепляется к живому ядру, поэтому годится и для сценария в тесте, и
    для записи настоящей сессии из приложения.
    """

    def __init__(self, engine, box=None, title=""):
        self._engine = engine
        self._box = box
        self.title = title
        self.steps = []
        self._original = None
        self._last_at = None

    def attach(self):
        engine = self._engine
        self._original = engine.handle_command

        def wrapper(text, require_wake=False, source="typed"):
            now = time.time()
            gap = 0.0 if self._last_at is None else round(now - self._last_at, 2)
            self._last_at = now

            spoken_before = len(getattr(self._box, "spoken", []) or [])
            said = []
            real_say = engine.say
            engine.say = lambda t, sound="response": (said.append(t),
                                                      real_say(t, sound=sound))[0]
            before = self._effects()
            try:
                self._original(text, require_wake=require_wake, source=source)
            finally:
                engine.say = real_say

            question = engine._dialog.current()
            self.steps.append({
                "say": text,
                "source": source,
                "wake": require_wake,
                "after": gap,
                "response": normalise(said[-1] if said else None),
                "effects": normalise_effects(self._effects_since(before)),
                "question": question.kind if question else None,
            })

        engine.handle_command = wrapper
        return self

    def detach(self):
        if self._original is not None:
            self._engine.handle_command = self._original
            self._original = None

    def _effects(self):
        box = self._box
        if box is None:
            return {}
        return {name: len(getattr(box, name)) for name in
                ("launched", "actions", "opened", "paths", "reminders")}

    def _effects_since(self, before):
        box = self._box
        if box is None:
            return {}
        out = {}
        for name, count in before.items():
            added = getattr(box, name)[count:]
            if added:
                out[name] = list(added)
        return out

    def to_dict(self):
        return {"format": 1, "title": self.title, "baseline": "3.1.0",
                "steps": self.steps}

    def save(self, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
        return path


# ---------------------------------------------------------------------------
# Воспроизведение
# ---------------------------------------------------------------------------
def build_engine():
    """Свежее ядро в песочнице, с настройками в памяти."""
    from core import logging_setup
    logging_setup.setup()

    from sandbox import neutralise
    box = neutralise()

    from core.engine import RinaEngine
    from core.events import EventBus
    from core.settings_api import MemorySettings
    from voice import app_index

    # Индекс фиксированный: сессия обязана воспроизводиться на любой машине.
    from golden_runner import FAKE_APPS
    app_index._INDEX = [app_index.AppEntry(*a) for a in FAKE_APPS]
    app_index.cached_index = lambda: app_index._INDEX
    app_index.get_index = lambda refresh=False: app_index._INDEX

    settings = MemorySettings({
        "llm_enabled": False, "web_search_fallback": True,
        "wake_words": ["Рина", "Rina"], "ui_language": "Русский",
    })
    engine = RinaEngine(event_bus=EventBus(), settings=settings)
    engine._speak_blocking = lambda text: None
    return engine, box


def replay(path, verbose=False):
    """Воспроизводит сессию и печатает расхождения."""
    data = json.load(open(path, encoding="utf-8"))
    engine, box = build_engine()

    clock = FakeClock().install()
    mismatches = []
    try:
        for number, step in enumerate(data["steps"], 1):
            clock.advance(step.get("after", 0))

            said = []
            real_say = engine.say
            engine.say = lambda t, sound="response": said.append(t)
            before = {name: len(getattr(box, name)) for name in
                      ("launched", "actions", "opened", "paths", "reminders")}
            engine.handle_command(step["say"],
                                  require_wake=step.get("wake", False),
                                  source=step.get("source", "typed"))
            engine.say = real_say

            got_response = normalise(said[-1] if said else None)
            got_effects = {}
            for name, count in before.items():
                added = getattr(box, name)[count:]
                if added:
                    got_effects[name] = list(added)
            got_effects = normalise_effects(got_effects)
            question = engine._dialog.current()
            got_question = question.kind if question else None

            problems = []
            if got_response != step.get("response"):
                problems.append(("ответ", step.get("response"), got_response))
            if got_effects != (step.get("effects") or {}):
                problems.append(("эффекты", step.get("effects"), got_effects))
            if got_question != step.get("question"):
                problems.append(("вопрос", step.get("question"), got_question))

            if problems:
                mismatches.append((number, step, problems))
            elif verbose:
                print(f"    шаг {number}: {step['say']!r} -> ок")
    finally:
        clock.uninstall()

    name = os.path.basename(path)
    if mismatches:
        print(f"  {name}: расхождений {len(mismatches)}")
        for number, step, problems in mismatches:
            print(f"    шаг {number}: {step['say']!r} "
                  f"(через {step.get('after', 0)} с)")
            for what, want, got in problems:
                print(f"      {what}: ожидалось {want!r}, получено {got!r}")
    else:
        print(f"  {name}: {len(data['steps'])} шагов, расхождений нет"
              f"  — {data.get('title', '')}")
    return len(mismatches)


def main():
    ap = argparse.ArgumentParser(description="Сессии: запись и воспроизведение")
    ap.add_argument("--replay", metavar="PATH")
    ap.add_argument("--replay-all", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    paths = sorted(glob.glob(os.path.join(SESSIONS_DIR, "*.json")))

    if args.list:
        for path in paths:
            data = json.load(open(path, encoding="utf-8"))
            print(f"{os.path.basename(path):32} {len(data['steps']):>2} шагов"
                  f"  {data.get('title', '')}")
        return 0

    if args.replay:
        return 1 if replay(args.replay, args.verbose) else 0

    if args.replay_all or True:
        if not paths:
            print("Сессий нет.")
            return 0
        print(f"Сессий: {len(paths)}")
        failed = sum(bool(replay(p, args.verbose)) for p in paths)
        print(f"\nСессий с расхождениями: {failed} из {len(paths)}")
        return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
