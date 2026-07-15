"""
Динамическая система тем.

Color — объект с атрибутами-цветами (BASE, TEXT, ACCENT, ...).
При смене темы атрибуты МУТИРУЮТСЯ, затем theme_manager.changed шлёт сигнал,
по которому каждый виджет пересобирает свой QSS через apply_theme().
Существующий код, обращающийся к Color.BASE как к строке, работает без правок.
"""

from PySide6.QtCore import QObject, Signal


FONT_FAMILY = "Segoe UI"


PAGE_ICONS = {
    "Рина":              "🌸",
    "Команды":           "⚡",
    "Горячие клавиши":   "⌨️",
    "История":           "🕑",
    "Настройки":         "⚙️",
    "О программе":       "ℹ️",
    "Плагины":           "🧩",
}


class Radius:
    SM = 8
    MD = 12
    LG = 18
    XL = 24


class Spacing:
    XS = 6
    SM = 10
    MD = 16
    LG = 24
    XL = 32


PALETTES = {
    "Catppuccin Mocha": {
        "BASE": "#11111b", "MANTLE": "#181825", "CRUST": "#1e1e2e",
        "SURFACE_0": "#313244", "SURFACE_1": "#45475a", "SURFACE_2": "#585b70",
        "TEXT": "#cdd6f4", "SUBTEXT": "#a6adc8", "OVERLAY": "#6c7086",
        "accents": {
            "Mauve": "#cba6f7", "Pink": "#f5c2e7", "Blue": "#89b4fa",
            "Green": "#a6e3a1", "Peach": "#fab387", "Teal": "#94e2d5",
        },
        "GREEN": "#a6e3a1", "RED": "#f38ba8", "PEACH": "#fab387",
        "YELLOW": "#f9e2af", "PINK": "#f5c2e7", "BLUE": "#89b4fa",
        "TEAL": "#94e2d5", "MAUVE": "#cba6f7",
    },
    "Catppuccin Macchiato": {
        "BASE": "#181926", "MANTLE": "#1e2030", "CRUST": "#24273a",
        "SURFACE_0": "#363a4f", "SURFACE_1": "#494d64", "SURFACE_2": "#5b6078",
        "TEXT": "#cad3f5", "SUBTEXT": "#a5adcb", "OVERLAY": "#6e738d",
        "accents": {
            "Mauve": "#c6a0f6", "Pink": "#f5bde6", "Blue": "#8aadf4",
            "Green": "#a6da95", "Peach": "#f5a97f", "Teal": "#8bd5ca",
        },
        "GREEN": "#a6da95", "RED": "#ed8796", "PEACH": "#f5a97f",
        "YELLOW": "#eed49f", "PINK": "#f5bde6", "BLUE": "#8aadf4",
        "TEAL": "#8bd5ca", "MAUVE": "#c6a0f6",
    },
    "Tokyo Night": {
        "BASE": "#1a1b26", "MANTLE": "#16161e", "CRUST": "#1f2335",
        "SURFACE_0": "#292e42", "SURFACE_1": "#3b4261", "SURFACE_2": "#545c7e",
        "TEXT": "#c0caf5", "SUBTEXT": "#a9b1d6", "OVERLAY": "#565f89",
        "accents": {
            "Mauve": "#bb9af7", "Pink": "#ff9edd", "Blue": "#7aa2f7",
            "Green": "#9ece6a", "Peach": "#ff9e64", "Teal": "#2ac3de",
        },
        "GREEN": "#9ece6a", "RED": "#f7768e", "PEACH": "#ff9e64",
        "YELLOW": "#e0af68", "PINK": "#ff9edd", "BLUE": "#7aa2f7",
        "TEAL": "#2ac3de", "MAUVE": "#bb9af7",
    },
    "Nord": {
        "BASE": "#2e3440", "MANTLE": "#2b303b", "CRUST": "#3b4252",
        "SURFACE_0": "#434c5e", "SURFACE_1": "#4c566a", "SURFACE_2": "#616e88",
        "TEXT": "#eceff4", "SUBTEXT": "#d8dee9", "OVERLAY": "#7b88a1",
        "accents": {
            "Mauve": "#b48ead", "Pink": "#b48ead", "Blue": "#81a1c1",
            "Green": "#a3be8c", "Peach": "#d08770", "Teal": "#88c0d0",
        },
        "GREEN": "#a3be8c", "RED": "#bf616a", "PEACH": "#d08770",
        "YELLOW": "#ebcb8b", "PINK": "#b48ead", "BLUE": "#81a1c1",
        "TEAL": "#88c0d0", "MAUVE": "#b48ead",
    },
    "Dracula": {
        "BASE": "#282a36", "MANTLE": "#21222c", "CRUST": "#343746",
        "SURFACE_0": "#44475a", "SURFACE_1": "#565872", "SURFACE_2": "#6272a4",
        "TEXT": "#f8f8f2", "SUBTEXT": "#c8c9d8", "OVERLAY": "#6272a4",
        "accents": {
            "Mauve": "#bd93f9", "Pink": "#ff79c6", "Blue": "#8be9fd",
            "Green": "#50fa7b", "Peach": "#ffb86c", "Teal": "#8be9fd",
        },
        "GREEN": "#50fa7b", "RED": "#ff5555", "PEACH": "#ffb86c",
        "YELLOW": "#f1fa8c", "PINK": "#ff79c6", "BLUE": "#8be9fd",
        "TEAL": "#8be9fd", "MAUVE": "#bd93f9",
    },
}

DEFAULT_THEME = "Catppuccin Mocha"
DEFAULT_ACCENT = "Mauve"


class _Color:
    """Держатель текущих цветов; атрибуты меняются при смене темы."""
    BASE = MANTLE = CRUST = ""
    SURFACE_0 = SURFACE_1 = SURFACE_2 = ""
    TEXT = SUBTEXT = OVERLAY = ""
    GREEN = RED = PEACH = YELLOW = PINK = BLUE = TEAL = MAUVE = ""
    ACCENT = ""

    def apply(self, theme_name, accent_name):
        pal = PALETTES.get(theme_name, PALETTES[DEFAULT_THEME])
        for key in ("BASE", "MANTLE", "CRUST", "SURFACE_0", "SURFACE_1",
                    "SURFACE_2", "TEXT", "SUBTEXT", "OVERLAY",
                    "GREEN", "RED", "PEACH", "YELLOW", "PINK", "BLUE",
                    "TEAL", "MAUVE"):
            setattr(self, key, pal[key])
        accents = pal["accents"]
        self.ACCENT = accents.get(accent_name, next(iter(accents.values())))


Color = _Color()


class _ThemeManager(QObject):
    changed = Signal()

    def __init__(self):
        super().__init__()
        self.theme = DEFAULT_THEME
        self.accent = DEFAULT_ACCENT
        Color.apply(self.theme, self.accent)

    def set_theme(self, theme_name):
        if theme_name in PALETTES:
            self.theme = theme_name
            Color.apply(self.theme, self.accent)
            self.changed.emit()

    def set_accent(self, accent_name):
        self.accent = accent_name
        Color.apply(self.theme, self.accent)
        self.changed.emit()

    def apply(self, theme_name, accent_name):
        self.theme = theme_name if theme_name in PALETTES else DEFAULT_THEME
        self.accent = accent_name
        Color.apply(self.theme, self.accent)
        self.changed.emit()

    def accent_names(self):
        return list(PALETTES[self.theme]["accents"].keys())

    def theme_names(self):
        return list(PALETTES.keys())


theme_manager = _ThemeManager()
