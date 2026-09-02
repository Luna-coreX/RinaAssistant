# -*- coding: utf-8 -*-
"""
Прогонщик набора golden utterances (задача плана 4.0-A03).

Гоняет набор фраз против ядра и печатает расхождения в виде
«фраза / ожидалось / получено». Пригоден для запуска после каждого коммита:
один вызов, понятный отчёт, код возврата 1 при любом расхождении.

Почему намерение, а не текст ответа. Набор должен пережить перенос ядра на
C#. Русский текст ответа для этого не годится: он переводится, переформулируется
и вообще принадлежит представлению. Ожидание записано как namespace-имя
намерения из `core/intent.py` с аргументами.

Почему драйвер. Сегодня ядро в том же процессе, после 4.0-E02 оно будет
отдельным процессом за протоколом. Набор и сравнение при этом не меняются —
меняется только способ задать фразу и получить намерение. Это и есть драйвер.

Почему индекс программ подменяется. Набор обязан давать один результат на
любой машине. Настоящий индекс зависит от того, что установлено.

Всё, что имеет побочный эффект, подменено: ни одна программа не запускается,
компьютер не выключается, браузер не открывается.

Запуск:
    python tools/golden_runner.py                 # весь набор
    python tools/golden_runner.py --verbose       # с прошедшими случаями
    python tools/golden_runner.py --groups app,reminder
    python tools/golden_runner.py --json out.json # для сборочной линии
"""

import argparse
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

# Каталог данных — во временную папку, и это надо сделать до создания первого
# хранилища. Подмены ниже закрывают то, что видно снаружи: звук, запуск
# программ, браузер. Хранилище они не закрывали, и набор писал историю
# разговоров и журнал вызовов в настоящие файлы пользователя.
from sandbox import isolate_storage
isolate_storage()

from core.dialog import Question
from core.intent import INTENTS, Intent, UnknownIntent, check_intent_name
from voice.app_index import AppEntry

DEFAULT_SET = os.path.join(ROOT, "docs", "golden", "utterances.json")


# ---------------------------------------------------------------------------
# Синтетический индекс программ
# ---------------------------------------------------------------------------
FAKE_APPS = [
    ("Telegram Desktop", r"C:\Apps\Telegram\Telegram.exe", "file", "start_menu"),
    ("Google Chrome", r"C:\Program Files\Google\Chrome\chrome.exe", "file", "start_menu"),
    ("Mozilla Firefox", r"C:\Program Files\Mozilla Firefox\firefox.exe", "file", "start_menu"),
    ("Visual Studio Code", r"C:\Apps\VSCode\Code.exe", "file", "start_menu"),
    ("Visual Studio 2022", r"C:\Apps\VS2022\devenv.exe", "file", "start_menu"),
    ("Discord", r"C:\Apps\Discord\Discord.exe", "file", "start_menu"),
    ("Steam", r"C:\Program Files\Steam\steam.exe", "file", "start_menu"),
    ("OBS Studio", r"C:\Program Files\obs-studio\obs64.exe", "file", "start_menu"),
    ("Blender", r"C:\Program Files\Blender\blender.exe", "file", "start_menu"),
    ("Notepad", r"C:\Windows\System32\notepad.exe", "file", "start_menu"),
    ("Калькулятор", "Microsoft.WindowsCalculator_8wekyb3d8bbwe!App", "uwp", "uwp"),
]


class Observed:
    """Что случилось при обработке одной фразы."""

    def __init__(self):
        self.said = []
        self.launched = []
        self.actions = []
        self.reminders = []
        self.events = []
        self.pending = None

    def clear(self):
        for name in ("said", "launched", "actions", "reminders", "events"):
            getattr(self, name).clear()
        self.pending = None

    def response(self):
        return self.said[-1] if self.said else None


# ---------------------------------------------------------------------------
# Драйверы
# ---------------------------------------------------------------------------
class Driver:
    """Способ задать ядру фразу и получить намерение."""

    name = "?"

    def setup(self):
        pass

    def send(self, text, source="typed", require_wake=False, keep_state=False):
        """Возвращает Intent."""
        raise NotImplementedError

    def teardown(self):
        pass


class InProcessDriver(Driver):
    """
    Ядро в том же процессе. Намерение выводится из наблюдаемых последствий.

    Это временная мера, и она честно отмечена: пока конвейер сам не объявляет
    намерение (4.0-B02 выделяет Router), прогонщик восстанавливает его по
    тому, что ядро сделало. После B02 драйвер будет брать Intent напрямую,
    а классификатор ниже исчезнет вместе с этим комментарием.
    """

    name = "in-process"

    def setup(self):
        from core import logging_setup
        logging_setup.setup()

        from core.settings_store import settings
        settings.load()
        settings.update({
            "first_run": False, "check_updates": False, "llm_enabled": False,
            "web_search_fallback": True, "save_history": True,
            "custom_commands": [], "app_aliases": {}, "reminders": [],
            "history": [], "ui_language": "Русский", "search_engine": "google",
            "wake_words": ["Рина", "Rina"],
        })
        settings.save()
        self.settings = settings

        from voice import app_index, system_control, sounds, websearch, reminders
        from core.engine import RinaEngine
        from core.events import EventBus
        from core.protocol import Events

        obs = Observed()
        self.obs = obs

        app_index._INDEX = [app_index.AppEntry(*a) for a in FAKE_APPS]
        app_index.cached_index = lambda: app_index._INDEX
        app_index.get_index = lambda refresh=False: app_index._INDEX
        app_index.launch = lambda e: (obs.launched.append(e.name), True)[1]

        for key in list(system_control.RUNNERS):
            system_control.RUNNERS[key] = (
                lambda k: (lambda: (obs.actions.append(k), True)[1]))(key)

        sounds.play_response = sounds.play_error = sounds.play_activation = \
            lambda s: None
        websearch.webbrowser.open = lambda url, *a, **k: True

        real_add = reminders.ReminderStore.add

        def spy_add(store, kind, fire_at, text=""):
            obs.reminders.append({"kind": kind, "fire_at": fire_at,
                                  "text": text})
            return real_add(store, kind, fire_at, text)

        reminders.ReminderStore.add = spy_add

        engine = RinaEngine(event_bus=EventBus())
        engine._speak_blocking = lambda text: None
        real_say = engine.say
        engine.say = lambda text, sound="response": (
            obs.said.append(text), real_say(text, sound=sound))[0]
        self.engine = engine

        # Одна шина — своего ядра. До 4.0-B05 приходилось слушать ещё и
        # модульный синглтон: system_control слал события мимо ядра.
        # Подписчик принимает полезную нагрузку одним словарём — см. EventBus.
        for name in (Events.APP_NOT_FOUND, Events.WINDOW_ACTION):
            engine.bus.on(name, (lambda n: (lambda data: obs.events.append(
                (n, data))))(name))

    def send(self, text, source="typed", require_wake=False, keep_state=False):
        if not keep_state:
            self.engine._dialog.dropped()
            self.settings.set("reminders", [])
            self.settings.set("app_aliases", {})
        self.obs.clear()
        self.engine.handle_command(text, require_wake=require_wake,
                                   source=source)
        # Заданный вопрос теперь живёт в core/dialog.py и сериализуем.
        question = self.engine._dialog.current()
        self.obs.pending = question.to_dict() if question else None
        return classify(self.obs, text)


class RouterDriver(Driver):
    """
    Роутер напрямую. Ни ядра, ни настроек, ни Qt, ни единого хранилища.

    Это критерий приёмки 4.0-B02: набор проверяет разбор, а не последствия.
    Всё, что роутер знает о мире, собрано здесь руками — поэтому результат
    одинаков на любой машине и не зависит от установленного софта.

    Состояние между случаями драйвер ведёт сам: у роутера его нет.
    """

    name = "router"

    def setup(self):
        from voice import app_index
        from core.router import RouterContext

        self.apps = [app_index.AppEntry(*a) for a in FAKE_APPS]
        self.aliases = {}
        self.reminders_active = 0
        self.pending = None
        self.ctx = RouterContext(apps=self.apps)

    def send(self, text, source="typed", require_wake=False, keep_state=False):
        from core.router import route

        if not keep_state:
            self.pending = None
            self.reminders_active = 0

        self.ctx.pending = self.pending
        self.ctx.source = source
        self.ctx.require_wake = require_wake
        self.ctx.reminders_active = self.reminders_active

        intent = route(text, self.ctx)

        # Последствия, которые меняют состояние следующего шага. Их
        # применяет исполнитель; здесь воспроизводится ровно столько,
        # сколько нужно многошаговым случаям набора.
        if intent.name == "reminder.create":
            self.reminders_active += 1
        elif intent.name == "reminder.cancel":
            self.reminders_active = 0
        elif intent.name == "app.ambiguous":
            self.pending = Question.choose_app(
                [AppEntry.from_dict(o) for o in intent.arg("options") or []],
                query=intent.arg("query") or "").to_dict()
        elif intent.name == "system.confirm":
            self.pending = Question.confirm_action(
                intent.arg("action")).to_dict()
        else:
            self.pending = None

        return intent


class ProtocolDriver(Driver):
    """
    Ядро отдельным процессом за именованным каналом.

    Появится вместе с 4.0-E02. Тогда `send` отправит `command.handle` и
    дождётся намерения ответом, а всё остальное в этом файле — набор,
    сравнение и отчёт — останется как есть. Ради этого и введён драйвер.
    """

    name = "protocol"

    def setup(self):
        raise NotImplementedError(
            "драйвер протокола появится вместе с 4.0-E02 (ядро как сервис)")


DRIVERS = {d.name: d for d in (InProcessDriver, RouterDriver,
                              ProtocolDriver)}


# ---------------------------------------------------------------------------
# Восстановление намерения по последствиям (до 4.0-B02)
# ---------------------------------------------------------------------------
def classify(obs, text=""):
    """Наблюдаемое поведение -> Intent."""

    def intent(name, **args):
        return Intent(name=name, args=args, stage="observed", text=text)

    if obs.launched:
        return intent("app.launch", app=obs.launched[-1])
    if obs.reminders:
        item = obs.reminders[-1]
        args = {"kind": item["kind"]}
        if item["text"]:
            args["text"] = item["text"]
        return intent("reminder.create", **args)
    if obs.actions:
        return intent("system.action", action=obs.actions[-1])

    if obs.pending:
        kind = obs.pending.get("kind")
        if kind == "choose_app":
            return intent("app.ambiguous", options=[
                o.get("name") for o in obs.pending.get("options") or []])
        if kind == "confirm_action":
            return intent("system.confirm",
                          action=obs.pending.get("action"))
        if kind == "confirm_command":
            return intent("command.confirm")

    names = [n for n, _ in obs.events]
    if "apps.not_found" in names:
        query = [d.get("query") for n, d in obs.events
                 if n == "apps.not_found"]
        return intent("app.not_found", query=query[-1] if query else None)
    if "window.action" in names:
        action = [d.get("action") for n, d in obs.events
                  if n == "window.action"]
        return intent("system.action", action=action[-1])

    response = obs.response()
    if response is None:
        return intent("silence")

    # Опорные строки — это ключи словаря переводов, а не переведённый текст:
    # они не меняются при смене языка интерфейса.
    table = [
        ("Да? Слушаю.", lambda r: intent("ask.wake")),
        ("Хорошо, отменяю.", lambda r: intent("cancelled")),
        ("На ноль делить нельзя.", lambda r: intent("calc.zero_division")),
        ("Извини, я не поняла команду.", lambda r: intent("fallback.none")),
        ("Ничего не запланировано.",
         lambda r: intent("reminder.list", empty=True)),
        ("Нечего отменять.",
         lambda r: intent("reminder.cancel", empty=True)),
        ("Всегда пожалуйста!",
         lambda r: intent("builtin.answer", topic="thanks")),
    ]
    for exact, make in table:
        if response == exact:
            return make(response)

    prefixes = [
        ("Получается ", lambda r: intent(
            "calc", result=r[len("Получается "):].rstrip("."))),
        ("Ищу «", lambda r: intent(
            "websearch", query=r.split("«", 1)[1].split("»")[0])),
        ("Не нашла такой команды", lambda r: intent(
            "fallback.search", query=r.split("«", 1)[1].split("»")[0])),
        ("Запланировано:", lambda r: intent("reminder.list", empty=False)),
        ("Отменила:", lambda r: intent("reminder.cancel", empty=False)),
        ("Не нашла программу", lambda r: intent("app.not_found")),
        ("Не получилось запустить", lambda r: intent("app.launch_failed")),
        ("Меня зовут", lambda r: intent("builtin.answer", topic="name")),
        ("Я могу запускать",
         lambda r: intent("builtin.answer", topic="capabilities")),
    ]
    for prefix, make in prefixes:
        if response.startswith(prefix):
            return make(response)

    return intent("unknown", response=response)


def matches(expected, got):
    """Совпало ли ожидание. Проверяются только заявленные аргументы."""
    if expected.get("intent") != got.name:
        return False
    for key, want in expected.items():
        if key in ("intent", "note"):
            continue
        value = got.arg(key)
        if isinstance(want, list):
            if not isinstance(value, list) or set(want) - set(value):
                return False
        elif str(value) != str(want):
            return False
    return True


# ---------------------------------------------------------------------------
def load_set(path):
    """Набор с проверкой имён намерений по каталогу ядра."""
    data = json.load(open(path, encoding="utf-8"))
    bad = []
    for case in data["cases"]:
        try:
            check_intent_name(case["expect"]["intent"])
        except UnknownIntent:
            bad.append((case["id"], case["expect"]["intent"]))
    if bad:
        lines = "\n".join(f"    {cid}: {name!r}" for cid, name in bad)
        raise UnknownIntent(
            f"в наборе имена, которых нет в core/intent.py:\n{lines}")
    return data


def run(path, groups=None, verbose=False, driver_name="in-process"):
    data = load_set(path)
    cases = data["cases"]
    if groups:
        cases = [c for c in cases
                 if any(c["id"].startswith(g) for g in groups)]

    driver = DRIVERS[driver_name]()
    driver.setup()

    started = time.perf_counter()
    passed, failures = 0, []
    for case in cases:
        got = driver.send(case["say"], source=case.get("source", "typed"),
                          require_wake=case.get("wake", False),
                          keep_state=case.get("keep_state", False))
        if matches(case["expect"], got):
            passed += 1
            if verbose:
                print(f"  OK   {case['id']:<38} {got}")
        else:
            failures.append((case, got))
    elapsed = time.perf_counter() - started
    driver.teardown()

    print(f"Набор:   {os.path.relpath(path, ROOT)}")
    print(f"Драйвер: {driver.name}")
    print(f"Случаев: {len(cases)}, прошло: {passed}, "
          f"расхождений: {len(failures)}, за {elapsed:.1f} с")

    if failures:
        print()
        for case, got in failures:
            expected = dict(case["expect"])
            note = expected.pop("note", None)
            print(f"  {case['id']}")
            print(f"    фраза      {case['say']!r}")
            print(f"    ожидалось  {expected}")
            print(f"    получено   {got}")
            if got.name == "unknown":
                print(f"    ответ      {got.arg('response')!r}")
            if note:
                print(f"    пометка    {note}")

    return {
        "set": os.path.relpath(path, ROOT),
        "driver": driver.name,
        "total": len(cases),
        "passed": passed,
        "failed": len(failures),
        "seconds": round(elapsed, 2),
        "failures": [
            {"id": c["id"], "say": c["say"], "expected": c["expect"],
             "got": g.to_dict()} for c, g in failures
        ],
    }


def main():
    ap = argparse.ArgumentParser(
        description="Прогонщик набора golden utterances")
    ap.add_argument("set", nargs="?", default=DEFAULT_SET,
                    help="путь к набору")
    ap.add_argument("--groups", default="",
                    help="префиксы идентификаторов через запятую")
    ap.add_argument("--verbose", action="store_true",
                    help="показывать и прошедшие случаи")
    ap.add_argument("--driver", default="in-process", choices=list(DRIVERS),
                    help="как обращаться к ядру")
    ap.add_argument("--json", metavar="PATH",
                    help="записать отчёт машинно-читаемым файлом")
    ap.add_argument("--catalog", action="store_true",
                    help="показать каталог намерений и выйти")
    args = ap.parse_args()

    if args.catalog:
        for name, description in sorted(INTENTS.items()):
            print(f"{name:22} {description}")
        return 0

    groups = [g.strip() for g in args.groups.split(",") if g.strip()]
    report = run(args.set, groups=groups, verbose=args.verbose,
                 driver_name=args.driver)

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"\nОтчёт: {args.json}")

    return 1 if report["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
