# -*- coding: utf-8 -*-
"""
The README's screenshots, taken again: `docs/screens/*.png`.

**Over a prepared profile, never over the person's.** The pictures that
stood in the README until 2026-09-29 were taken of a live Rina: the home
screen showed the track the developer was listening to, cover art with a
stranger's face included, and the dialogue showed their own conversation.
A product page is public, and what is on it must be what anybody would see
on a new installation after a few minutes of use — not somebody's evening.

So a profile is filled first, through the core's own engine: a few commands
typed as a person would type them, two commands of one's own saved, one
word learned. Then the shell draws each section of
that profile into a PNG (`--check-core --shot … --section …`), in a mode
that does not read the system's media register at all.

To run (the shell must be built):
    python tools/take_screens.py
"""
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

from console import child_env, use_utf8  # noqa: E402

use_utf8()

SHELL = os.path.join(ROOT, "shell", "Rina.Shell", "bin", "Debug",
                     "net9.0-windows10.0.19041.0", "Rina.Shell.exe")
SCREENS = os.path.join(ROOT, "docs", "screens")

#: Section -> file. The names the README already uses.
SECTIONS = [("home", "home"), ("dialog", "dialog"), ("commands", "commands"),
            ("reminders", "reminders"), ("plugins", "plugins"),
            ("privacy", "privacy"), ("settings", "settings")]

#: What a person might have said in their first few minutes.
#: Only what the core answers by itself: the profile is filled without
#: plugins, and a first try that asked a plugin left «Извини, я не поняла
#: команду» on the privacy page.
SAID = [
    "поставь таймер на 10 минут",
    "посчитай 15 умножить на 12",
    "напомни через 20 минут позвонить маме",
    "напомни в 19:30 проверить почту",
    "запиши в дела купить хлеб",
    "запиши в дела ответить на письмо",
    "запусти блокнот",
    "когда я говорю записная книжка, запускай блокнот",
]

#: And two commands of their own, saved as the commands page saves them.
OWN = [
    {"type": "app", "enabled": True, "triggers": ["рабочий режим"],
     "target": "notepad.exe"},
    {"type": "website", "enabled": True, "triggers": ["открой почту"],
     "target": "https://mail.example.com"},
]


def fill():
    """
    Fill the profile this process was started over (`APPDATA`).

    Through the core's own engine, in this process: the same router, the
    same stores, the same formats a running core writes. Run in a process
    of its own so that every store is created over the prepared folder and
    none of them has looked at the person's first.
    """
    from core.engine import RinaEngine
    from core.events import EventBus
    from core.settings_store import settings

    engine = RinaEngine(settings=settings, event_bus=EventBus())
    engine.voice_out = lambda text, **kw: None
    engine.browser_out = lambda url: (True, "")
    engine.launch_out = lambda path, kind: (True, "")
    engine.apps_source = lambda: [{
        "name": "Блокнот", "launch": "C:/Windows/System32/notepad.exe",
        "kind": "file", "source": "start_menu"}]
    for phrase in SAID:
        engine.handle_command(phrase)
        print("  сказано:", phrase)
    for command in OWN:
        engine._cmd_store.add(dict(command))
        print("  своя команда:", command["triggers"][0])
    settings.save_all()


def shoot(home):
    os.makedirs(SCREENS, exist_ok=True)
    env = child_env(RINA_SANDBOX_DIR=home, APPDATA=home)
    wanted = [one for one in sys.argv[1:] if not one.startswith("-")]
    for section, name in SECTIONS:
        if wanted and name not in wanted:
            continue
        target = os.path.join(SCREENS, f"{name}.png")
        done = subprocess.run([SHELL, "--check-core", "--shot", target,
                               "--section", section], env=env,
                              capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=300)
        print(f"  {name}.png", "готов" if os.path.exists(target) and
              done.returncode == 0 else f"не вышел ({done.returncode})")


def main():
    if not os.path.exists(SHELL):
        print("оболочка не собрана:", SHELL)
        return 1
    home = tempfile.mkdtemp(prefix="rina-screens-")
    try:
        print("=== профиль ===")
        subprocess.run([sys.executable, "-u", os.path.abspath(__file__),
                        "--fill"], env=child_env(APPDATA=home,
                                                 XDG_CONFIG_HOME=home),
                       check=True, timeout=300)
        print("=== снимки ===")
        shoot(home)
    finally:
        shutil.rmtree(home, ignore_errors=True)
    return 0


if __name__ == "__main__":
    if "--fill" in sys.argv:
        fill()
        sys.exit(0)
    sys.exit(main())
