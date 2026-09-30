"""
The availability of capabilities.

Plan item 4.0-B08. In the beta there are no paid capabilities and every
answer is "available". Then why an interface now?

Because an availability check added later spreads through the code: a
condition in the pipeline, a second in the shell, a third in the settings —
and six months on nobody can say where exactly it is decided what a user may
do. One interface, created before the first paid capability appears, turns
that into replacing an implementation instead of edits all over the project.

Three rules it exists for:

    * **The core decides, the shell shows.** The shell asks and draws the
      state; it has no right to decide availability, or the decision ends up
      in two places at once and the shell can be circumvented.
    * **There must be no checks that bypass this interface.** Neither
      `plan == "pro"`, nor "if there is a licence", nor a flag in the
      settings.
    * **In the beta everything is available.** Not because we forgot but
      because it is a decision: the beta tests the product's usefulness, not
      the payment infrastructure.

There is no Qt here: the module lies in the core.
"""

from typing import Protocol, runtime_checkable


#: Capabilities that may some day become paid.
#:
#: The list is not a promise but a dictionary of names: it exists so that a
#: capability's name is written the same way in the core, in the shell and
#: in a future licence server. Not one of them is limited today.
FEATURES = {
    "rag":            "Поиск по локальным документам",
    "agents":         "Многошаговые сценарии с подтверждением",
    "sessions":       "Расширенная память рабочих сессий",
    "computer_use":   "Управление компьютером с предпросмотром",
    "sync":           "Зашифрованная синхронизация между устройствами",
    "connector.github": "Интеграция с GitHub",
    "connector.notion": "Интеграция с Notion",
    "vrm":            "Компаньон на рабочем столе",
    "workflow_packs": "Готовые наборы сценариев",
}

#: The plan the application is running under right now.
COMMUNITY = "community"


class UnknownFeature(ValueError):
    """The name is not in the capability dictionary."""


def check_feature_name(name):
    """A checked name, or UnknownFeature.

    A typo in a name would otherwise mean a quietly switched-off capability:
    `has_feature("agent")` instead of `"agents"` would return False and look
    like an honest refusal.
    """
    if name not in FEATURES:
        raise UnknownFeature(f"неизвестная возможность: {name!r}")
    return name


@runtime_checkable
class FeatureProvider(Protocol):
    """What the core needs to know about availability."""

    def plan(self) -> str:
        """The current plan's name — for showing, not for branching."""
        ...

    def has_feature(self, feature: str) -> bool:
        """Whether the capability is available."""
        ...

    def enabled_features(self) -> set:
        """Everything that is available right now."""
        ...


class CommunityFeatures:
    """
    The free plan: everything is available.

    This is the implementation as of 4.0. It is not a stub: the local base
    stays free even after paid plans appear, so the class itself will
    outlive their appearance — a second one will simply stand beside it.
    """

    def plan(self):
        return COMMUNITY

    def has_feature(self, feature):
        check_feature_name(feature)
        return True

    def enabled_features(self):
        return set(FEATURES)


class LimitedFeatures:
    """
    A limited set. Exists for the sake of the tests and so that code asking
    about availability is checkable BEFORE a paid plan appears.
    """

    def __init__(self, allowed=(), plan_name="test"):
        self._allowed = {check_feature_name(f) for f in allowed}
        self._plan = plan_name

    def plan(self):
        return self._plan

    def has_feature(self, feature):
        check_feature_name(feature)
        return feature in self._allowed

    def enabled_features(self):
        return set(self._allowed)


def default_features():
    """The default implementation."""
    return CommunityFeatures()
