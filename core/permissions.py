"""
The permission catalogue.

Plan item 4.0-C04. A list of what may be allowed at all, and the matrix
"tool → required permissions" (that lives in the tool's description, see
core/tools.py).

Why create it now, when everything is allowed. A permission added after a
tool is written gets added in the wrong place: it is put before the call,
and the way around it stays. A list created before the implementation makes
every new tool answer the question "and what do you need" at the moment it
is declared.

Two permissions are declared **in advance**: reading the screen and
synthesising input are needed only in 5.0, but the permission model around
them is thought through while that costs a paragraph rather than a rewrite
of the registry.

There is no Qt here: the module lies in the core.
"""

from typing import NamedTuple


class Permission(NamedTuple):
    """One permission: what it is, how dangerous it is, and what it is for."""

    name: str
    title: str
    #: A dangerous permission requires confirmation on every use rather than
    #: being granted once.
    dangerous: bool
    #: An explanation for the user — it will go onto the permission-granting
    #: screen (5.0-C02), so it is written in human language, not in terms.
    why: str


PERMISSIONS = {p.name: p for p in (
    Permission(
        "process.launch", "Запуск программ", False,
        "Открывать приложения и папки, которые вы называете."),
    Permission(
        "system.media", "Громкость и воспроизведение", False,
        "Менять громкость и управлять плеером."),
    Permission(
        "system.lock", "Блокировка экрана", False,
        "Блокировать рабочий стол по команде."),
    Permission(
        "system.power", "Выключение компьютера", True,
        "Выключать, перезагружать и усыплять компьютер. "
        "Каждое такое действие подтверждается отдельно."),
    Permission(
        "screen.capture", "Снимок экрана", False,
        "Делать снимок экрана и сохранять его в «Изображения»."),
    Permission(
        "network.local", "Обращение к локальным службам", False,
        "Спрашивать языковую модель, работающую на этом компьютере."),
    Permission(
        "network.external", "Выход в интернет", False,
        "Открывать поиск в браузере и обращаться к службам вне "
        "этого компьютера."),
    Permission(
        "files.read", "Чтение файлов", False,
        "Читать файлы, которые вы указали."),
    Permission(
        "files.write", "Запись файлов", True,
        "Создавать и изменять файлы."),
    # --- created in advance, used from 5.0 ---
    Permission(
        "screen.read", "Чтение содержимого экрана", True,
        "Видеть, что происходит на экране. Понадобится, когда Рина "
        "научится работать с компьютером."),
    Permission(
        "input.synthesize", "Управление мышью и клавиатурой", True,
        "Нажимать и печатать от вашего имени. Понадобится, когда Рина "
        "научится работать с компьютером."),
)}


#: Permissions that are never granted to a plugin (`4.0-H06`).
#:
#: The catalogue is **one** for the plugin and for the core: a second one,
#: "for plugins", would mean two languages about one and the same thing and
#: an inevitable divergence — a permission called "network" here and
#: "internet" there. But not all of it is available.
#:
#: Shutting the computer down at somebody else's code's decision is not what
#: a weather plugin is installed for. Writing files means somebody else's
#: name in a person's directories. The last two are reserved for 5.0 and do
#: not exist on a single tool at all.
#:
#: The list is checked rather than assumed: a test compares it with the
#: catalogue and with the built-in plugins' declarations.
PLUGIN_FORBIDDEN = frozenset({
    "system.power",
    "files.write",
    "screen.read",
    "input.synthesize",
})


def plugin_allowed(names):
    """
    What of what was asked for a plugin may have. Returns (allowed, denied).

    A refusal here is not an error but an answer: the plugin may have asked
    in advance, and the person must see what exactly it was not given.
    """
    wanted = {str(n) for n in (names or [])}
    unknown = {n for n in wanted if n not in PERMISSIONS}
    refused = (wanted & PLUGIN_FORBIDDEN) | unknown
    return sorted(wanted - refused), sorted(refused)


#: Permissions that in 4.0 do not exist on a single tool.
#: As a separate list, so that "not used" is a statement rather than an
#: observation: a test compares it with the real matrix.
RESERVED = frozenset({"screen.read", "input.synthesize"})


class UnknownPermission(ValueError):
    """The name is not in the catalogue."""


def check_permission(name):
    """A checked name, or UnknownPermission.

    A typo would otherwise create a permission nobody grants, and a tool
    would quietly stop working.
    """
    if name not in PERMISSIONS:
        raise UnknownPermission(f"неизвестное разрешение: {name!r}")
    return name


def dangerous(names):
    """Is at least one of those listed dangerous?"""
    return any(PERMISSIONS[check_permission(n)].dangerous for n in names)


def describe(names):
    """A human list — for the permission-granting screen."""
    return [PERMISSIONS[check_permission(n)] for n in sorted(names)]
