# -*- coding: utf-8 -*-
"""
The runner for the golden utterances suite (plan item 4.0-A03).

Drives a set of phrases against the core and prints the divergences as
"phrase / expected / got". Fit for running after every commit: one call, an
intelligible report, an exit code of 1 on any divergence.

Why the intent rather than the answer's text. The suite must survive the
core being ported to C#. Russian answer text will not do for that: it is
translated, reworded and belongs to the presentation anyway. The expectation
is written down as the namespace name of an intent from `core/intent.py`,
with arguments.

Why a driver. Today the core is in the same process; after 4.0-E02 it will
be a separate process behind the protocol. The suite and the comparison do
not change for that — only the way a phrase is given and an intent received.
That is what the driver is.

Why the program index is substituted. The suite must give one result on any
machine. A real index depends on what is installed.

Everything with a side effect is substituted: not one program is launched,
the computer is not shut down, the browser is not opened.

To run:
    python tools/golden_runner.py                 # the whole suite
    python tools/golden_runner.py --verbose       # with the cases that passed
    python tools/golden_runner.py --groups app,reminder
    python tools/golden_runner.py --json out.json # for the build line
"""

import argparse
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

# The data directory goes into a temporary folder, and that has to be done
# before the first store is created. The substitutions below cover what is
# visible from outside: the sound, launching programs, the browser. They did
# not cover the store, and the suite wrote the conversation history and the
# call journal into the user's real files.
from sandbox import isolate_storage
isolate_storage()

from core.dialog import Question
from core.intent import INTENTS, Intent, UnknownIntent, check_intent_name
from voice.app_index import AppEntry

DEFAULT_SET = os.path.join(ROOT, "docs", "golden", "utterances.json")


# ---------------------------------------------------------------------------
# The synthetic program index
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
    """What happened while one phrase was handled."""

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
# The drivers
# ---------------------------------------------------------------------------
class Driver:
    """A way of giving the core a phrase and getting an intent."""

    name = "?"

    def setup(self):
        pass

    def send(self, text, source="typed", require_wake=False, keep_state=False):
        """Returns an Intent."""
        raise NotImplementedError

    def teardown(self):
        pass


class InProcessDriver(Driver):
    """
    The core in the same process. The intent is derived from the observable
    consequences.

    This is a temporary measure, and it is honestly marked as one: until the
    pipeline declares the intent itself (4.0-B02 separates out the Router),
    the runner reconstructs it from what the core did. After B02 the driver
    will take the Intent directly, and the classifier below will disappear
    along with this comment.
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

        # The shell, which is not here. Since 4.0-G01 the core asks it to
        # perform a system action and to launch a program (ADR 0009), and it
        # is precisely that which has to be substituted — the core no longer
        # calls the `system_control.RUNNERS` functions at all. We record the
        # request and answer "it worked": the suite checks that the core
        # **decided** correctly, not that Windows can turn the volume up.
        def as_shell_do(action):
            obs.actions.append(action)
            return True, ""

        def as_shell_launch(launch, kind="file"):
            entry = next((e for e in app_index.cached_index()
                          if e.launch == launch), None)
            obs.launched.append(entry.name if entry else launch)
            return True, ""

        engine.system_out = as_shell_do
        engine.launch_out = as_shell_launch
        real_say = engine.say
        engine.say = lambda text, sound="response": (
            obs.said.append(text), real_say(text, sound=sound))[0]
        self.engine = engine

        # One bus — our own core's. Before 4.0-B05 the module singleton had
        # to be listened to as well: system_control sent events past the
        # core. A subscriber takes the payload as one dict — see EventBus.
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
        # The question asked now lives in core/dialog.py and is serialisable.
        question = self.engine._dialog.current()
        self.obs.pending = question.to_dict() if question else None
        return classify(self.obs, text)


class RouterDriver(Driver):
    """
    The router directly. No core, no settings, no Qt, not a single store.

    This is 4.0-B02's acceptance criterion: the suite checks the parse, not
    the consequences. Everything the router knows about the world is
    assembled here by hand — so the result is the same on any machine and
    does not depend on the software installed.

    The driver keeps the state between cases itself: the router has none.
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

        # The consequences that change the next step's state. The executor
        # applies them; reproduced here is exactly as much as the suite's
        # multi-step cases need.
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
    The core as a separate process behind a named pipe.

    It will appear along with 4.0-E02. Then `send` will send
    `command.handle` and wait for the intent as the answer, and everything
    else in this file — the suite, the comparison and the report — will stay
    as it is. That is what the driver was introduced for.
    """

    name = "protocol"

    def setup(self):
        raise NotImplementedError(
            "драйвер протокола появится вместе с 4.0-E02 (ядро как сервис)")


DRIVERS = {d.name: d for d in (InProcessDriver, RouterDriver,
                              ProtocolDriver)}


# ---------------------------------------------------------------------------
# Reconstructing the intent from the consequences (until 4.0-B02)
# ---------------------------------------------------------------------------
def classify(obs, text=""):
    """Observable behaviour -> an Intent."""

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

    # The reference strings are keys of the translation dictionary rather
    # than translated text: they do not change with the interface language.
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
    """Did the expectation match. Only the arguments stated are checked."""
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
    """The suite, with the intents' names checked against the core's catalogue."""
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
