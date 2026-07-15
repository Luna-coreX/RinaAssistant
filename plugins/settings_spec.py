"""
Декларативное описание настроек плагина.

Плагин описывает свои настройки списком полей (не касаясь Qt), а приложение
само строит панель и хранит значения в общем конфиге (plugin_settings).

Пример в плагине:

    from plugins.api import Plugin
    from plugins.settings_spec import Toggle, Text, Choice, Slider

    class MyPlugin(Plugin):
        def settings_schema(self):
            return [
                Text("city", "Город", default="Керкраде"),
                Toggle("celsius", "В градусах Цельсия", default=True),
                Choice("units", "Единицы", options=["метрические", "имперские"]),
                Slider("refresh", "Период обновления (мин)", min=1, max=60, default=15),
            ]
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Field:
    key: str
    label: str
    kind: str = "text"
    default: object = None
    description: str = ""
    icon: str = ""

    # для choice
    options: Optional[List[str]] = None
    # для slider
    min: int = 0
    max: int = 100
    step: int = 1


def Toggle(key, label, default=False, description="", icon="🔘"):
    return Field(key=key, label=label, kind="toggle", default=bool(default),
                 description=description, icon=icon)


def Text(key, label, default="", description="", icon="✏️"):
    return Field(key=key, label=label, kind="text", default=str(default),
                 description=description, icon=icon)


def Choice(key, label, options, default=None, description="", icon="📋"):
    opts = list(options or [])
    return Field(key=key, label=label, kind="choice", options=opts,
                 default=default if default is not None else (opts[0] if opts else ""),
                 description=description, icon=icon)


def Slider(key, label, min=0, max=100, default=None, step=1, description="", icon="🎚️"):
    return Field(key=key, label=label, kind="slider", min=min, max=max, step=step,
                 default=default if default is not None else min,
                 description=description, icon=icon)
