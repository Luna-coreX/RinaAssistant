"""
Автопанель настроек плагина.

Принимает схему (список Field из settings_spec) и plugin_id, строит контролы
нашими стилями и сохраняет значения через менеджер (plugin_settings в конфиге).
Плагину не нужно знать про Qt — достаточно вернуть settings_schema().
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel
from PySide6.QtGui import QFont
from PySide6.QtCore import Qt

from core.theme import Color, FONT_FAMILY
from components.card import Card
from components.toggle_switch import ToggleSwitch
from components.controls import (
    styled_combo, styled_lineedit, styled_slider, SettingRow, Divider
)


class PluginSettingsPanel(Card):
    """Карточка с настройками плагина, построенная из схемы."""

    def __init__(self, plugin_id, schema, manager, parent=None):
        super().__init__(parent)
        self._pid = plugin_id
        self._manager = manager
        self._schema = schema or []
        self._widgets = {}
        self._build()

    def _get(self, key, default):
        return self._manager.get_plugin_setting(self._pid, key, default)

    def _set(self, key, value):
        self._manager.set_plugin_setting(self._pid, key, value)

    def _build(self):
        cl = self.layout()
        title = QLabel("Настройки плагина")
        title.setFont(QFont(FONT_FAMILY, 13, QFont.Bold))
        title.setStyleSheet(f"color: {Color.SUBTEXT};")
        cl.addWidget(title)
        cl.addSpacing(2)

        for i, field in enumerate(self._schema):
            row = self._build_field(field)
            if row is not None:
                cl.addWidget(row)
                if i < len(self._schema) - 1:
                    cl.addWidget(Divider())

    def _build_field(self, field):
        kind = field.kind
        icon = field.icon or "•"

        if kind == "toggle":
            w = ToggleSwitch(checked=bool(self._get(field.key, field.default)))
            w.toggled.connect(lambda on, k=field.key: self._set(k, bool(on)))
            self._widgets[field.key] = w
            return SettingRow(icon, field.label, field.description, w)

        if kind == "text":
            w = styled_lineedit("", str(self._get(field.key, field.default)))
            w.textChanged.connect(lambda t, k=field.key: self._set(k, t))
            self._widgets[field.key] = w
            return SettingRow(icon, field.label, field.description, w)

        if kind == "choice":
            opts = field.options or []
            w = styled_combo(opts, 0)
            cur = self._get(field.key, field.default)
            if cur in opts:
                w.setCurrentIndex(opts.index(cur))
            w.currentTextChanged.connect(lambda t, k=field.key: self._set(k, t))
            self._widgets[field.key] = w
            return SettingRow(icon, field.label, field.description, w)

        if kind == "slider":
            container = QWidget()
            h = QHBoxLayout(container)
            h.setContentsMargins(0, 0, 0, 0)
            h.setSpacing(10)
            s = styled_slider(field.min, field.max,
                              int(self._get(field.key, field.default)))
            s.setFixedWidth(180)
            val = QLabel(str(s.value()))
            val.setStyleSheet(f"color: {Color.ACCENT}; font-weight: 600; font-size: 12px;")
            val.setFixedWidth(38)
            s.valueChanged.connect(lambda v: val.setText(str(v)))
            s.valueChanged.connect(lambda v, k=field.key: self._set(k, int(v)))
            h.addWidget(s)
            h.addWidget(val)
            self._widgets[field.key] = s
            return SettingRow(icon, field.label, field.description, container)

        return None
