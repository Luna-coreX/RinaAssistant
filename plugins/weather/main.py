"""
Weather Widget Plugin for RinaAssistant 4.0
Demonstrates: pages, navigation, i18n (RU/EN), settings integration
"""

from plugins.api import PluginHost, CommandSpec, PageSpec, SettingsSpec
from core.i18n import t, set_language, get_language
from typing import Optional
import random


class WeatherPlugin:
    """Weather widget plugin with localization and custom page"""
    
    def __init__(self, host: PluginHost):
        self.host = host
        self._current_temp: Optional[int] = None
        self._current_city: str = "Moscow"
        
        # Register plugin components
        self._register_commands()
        self._register_page()
        self._register_settings()
        self._register_localization()
    
    def _register_commands(self) -> None:
        """Register voice/text commands"""
        self.host.register_command(
            CommandSpec(
                id="weather_check",
                patterns_en=["weather", "check weather", "what's the weather", "temperature"],
                patterns_ru=["погода", "какая погода", "температура", "проверить погоду"],
                description_en="Check current weather",
                description_ru="Проверить текущую погоду",
                handler=self._handle_weather_command
            )
        )
        
        self.host.register_command(
            CommandSpec(
                id="weather_set_city",
                patterns_en=["set city *", "change city to *", "weather in *"],
                patterns_ru=["установить город *", "сменить город на *", "погода в *"],
                description_en="Set city for weather widget",
                description_ru="Установить город для виджета погоды",
                handler=self._handle_set_city
            )
        )
    
    def _register_page(self) -> None:
        """Register custom page with navigation"""
        self.host.register_page(
            PageSpec(
                id="weather_page",
                title_en="Weather",
                title_ru="Погода",
                icon="🌤️",
                navigation_group="widgets",
                navigation_order=10,
                factory=self._create_weather_page
            )
        )
    
    def _register_settings(self) -> None:
        """Register plugin settings"""
        self.host.register_settings(
            SettingsSpec(
                id="weather_settings",
                title_en="Weather Widget",
                title_ru="Виджет погоды",
                fields=[
                    {
                        "id": "city",
                        "type": "text",
                        "label_en": "City",
                        "label_ru": "Город",
                        "default": "Moscow"
                    },
                    {
                        "id": "units",
                        "type": "select",
                        "label_en": "Temperature Units",
                        "label_ru": "Единицы температуры",
                        "options": [
                            {"value": "celsius", "label_en": "Celsius (℃)", "label_ru": "Цельсий (℃)"},
                            {"value": "fahrenheit", "label_en": "Fahrenheit (℉)", "label_ru": "Фаренгейт (℉)"}
                        ],
                        "default": "celsius"
                    },
                    {
                        "id": "auto_refresh",
                        "type": "boolean",
                        "label_en": "Auto-refresh every hour",
                        "label_ru": "Автообновление каждый час",
                        "default": True
                    }
                ]
            )
        )
    
    def _register_localization(self) -> None:
        """Register localization strings"""
        self.host.register_i18n_bundle("weather", {
            "en": {
                "welcome": "Welcome to Weather Widget!",
                "current_temp": "Current temperature in {city}: {temp}℃",
                "condition_sunny": "Sunny ☀️",
                "condition_cloudy": "Cloudy ☁️",
                "condition_rainy": "Rainy 🌧️",
                "condition_snowy": "Snowy ❄️",
                "refresh_btn": "Refresh",
                "settings_btn": "Settings",
                "city_label": "City:",
                "feels_like": "Feels like {temp}℃",
                "humidity": "Humidity: {value}%",
                "no_city_set": "No city set. Open settings to configure.",
                "last_updated": "Last updated: {time}"
            },
            "ru": {
                "welcome": "Добро пожаловать в Виджет Погоды!",
                "current_temp": "Текущая температура в {city}: {temp}℃",
                "condition_sunny": "Солнечно ☀️",
                "condition_cloudy": "Облачно ☁️",
                "condition_rainy": "Дождь 🌧️",
                "condition_snowy": "Снег ❄️",
                "refresh_btn": "Обновить",
                "settings_btn": "Настройки",
                "city_label": "Город:",
                "feels_like": "Ощущается как {temp}℃",
                "humidity": "Влажность: {value}%",
                "no_city_set": "Город не установлен. Откройте настройки для конфигурации.",
                "last_updated": "Последнее обновление: {time}"
            }
        })
    
    def _handle_weather_command(self, context: dict) -> str:
        """Handle weather check command"""
        settings = self.host.get_settings("weather_settings")
        city = settings.get("city", self._current_city)
        
        # Simulate weather data (in real plugin would call API)
        temp = self._get_simulated_temp(city)
        condition = self._get_simulated_condition()
        
        lang = get_language()[:2]
        if lang == "ru":
            return f"В {city} сейчас {condition}. Температура: {temp}℃"
        else:
            return f"In {city} it's {condition}. Temperature: {temp}℃"
    
    def _handle_set_city(self, context: dict, city: str = None) -> str:
        """Handle set city command"""
        if city:
            self.host.update_settings("weather_settings", {"city": city})
            self._current_city = city
            lang = get_language()[:2]
            if lang == "ru":
                return f"Город установлен: {city}"
            else:
                return f"City set to: {city}"
        else:
            lang = get_language()[:2]
            if lang == "ru":
                return "Пожалуйста, укажите город. Пример: 'установить город Москва'"
            else:
                return "Please specify a city. Example: 'set city Moscow'"
    
    def _create_weather_page(self, parent) -> object:
        """Create the weather page UI"""
        from PySide6.QtWidgets import (
            QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
            QPushButton, QFrame, QSizePolicy
        )
        from PySide6.QtCore import Qt, QTimer
        from PySide6.QtGui import QFont
        
        class WeatherPageWidget(QWidget):
            def __init__(self, plugin: WeatherPlugin, parent=None):
                super().__init__(parent)
                self.plugin = plugin
                self.setup_ui()
                self.refresh_weather()
                
                # Auto-refresh timer
                self.timer = QTimer()
                self.timer.timeout.connect(self.refresh_weather)
                settings = self.plugin.host.get_settings("weather_settings")
                if settings.get("auto_refresh", True):
                    self.timer.start(3600000)  # 1 hour
            
            def setup_ui(self):
                layout = QVBoxLayout(self)
                layout.setSpacing(16)
                layout.setContentsMargins(20, 20, 20, 20)
                
                # Title
                title = QLabel(self._t("welcome"))
                title.setFont(QFont("Segoe UI", 18, QFont.Bold))
                title.setAlignment(Qt.AlignCenter)
                layout.addWidget(title)
                
                # Weather card
                card = QFrame()
                card.setObjectName("weatherCard")
                card.setStyleSheet("""
                    QFrame#weatherCard {
                        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                            stop:0 #4A90E2, stop:1 #0066CC);
                        border-radius: 12px;
                        padding: 20px;
                    }
                    QLabel {
                        color: white;
                    }
                """)
                card_layout = QVBoxLayout(card)
                card_layout.setSpacing(12)
                
                # City label
                self.city_label = QLabel()
                self.city_label.setFont(QFont("Segoe UI", 14))
                self.city_label.setAlignment(Qt.AlignCenter)
                card_layout.addWidget(self.city_label)
                
                # Temperature
                self.temp_label = QLabel()
                self.temp_label.setFont(QFont("Segoe UI", 36, QFont.Bold))
                self.temp_label.setAlignment(Qt.AlignCenter)
                card_layout.addWidget(self.temp_label)
                
                # Condition
                self.condition_label = QLabel()
                self.condition_label.setFont(QFont("Segoe UI", 14))
                self.condition_label.setAlignment(Qt.AlignCenter)
                card_layout.addWidget(self.condition_label)
                
                # Details row
                details_layout = QHBoxLayout()
                
                self.feels_like_label = QLabel()
                self.feels_like_label.setAlignment(Qt.AlignCenter)
                details_layout.addWidget(self.feels_like_label)
                
                self.humidity_label = QLabel()
                self.humidity_label.setAlignment(Qt.AlignCenter)
                details_layout.addWidget(self.humidity_label)
                
                card_layout.addLayout(details_layout)
                
                # Last updated
                self.updated_label = QLabel()
                self.updated_label.setFont(QFont("Segoe UI", 9))
                self.updated_label.setAlignment(Qt.AlignCenter)
                self.updated_label.setStyleSheet("color: rgba(255,255,255,0.7)")
                card_layout.addWidget(self.updated_label)
                
                layout.addWidget(card)
                
                # Action buttons
                btn_layout = QHBoxLayout()
                btn_layout.setSpacing(12)
                
                self.refresh_btn = QPushButton(self._t("refresh_btn"))
                self.refresh_btn.clicked.connect(self.refresh_weather)
                self.refresh_btn.setStyleSheet("""
                    QPushButton {
                        background: #4A90E2;
                        color: white;
                        border: none;
                        border-radius: 8px;
                        padding: 12px 24px;
                        font-size: 14px;
                        font-weight: bold;
                    }
                    QPushButton:hover {
                        background: #357ABD;
                    }
                    QPushButton:pressed {
                        background: #2A5F8F;
                    }
                """)
                btn_layout.addWidget(self.refresh_btn)
                
                self.settings_btn = QPushButton(self._t("settings_btn"))
                self.settings_btn.clicked.connect(self._open_settings)
                self.settings_btn.setStyleSheet("""
                    QPushButton {
                        background: #6C757D;
                        color: white;
                        border: none;
                        border-radius: 8px;
                        padding: 12px 24px;
                        font-size: 14px;
                        font-weight: bold;
                    }
                    QPushButton:hover {
                        background: #5A6368;
                    }
                    QPushButton:pressed {
                        background: #495057;
                    }
                """)
                btn_layout.addWidget(self.settings_btn)
                
                layout.addLayout(btn_layout)
                
                # Spacer
                layout.addStretch()
            
            def _t(self, key: str, **kwargs) -> str:
                """Translate string"""
                lang = get_language()[:2]
                bundle = self.plugin.host.get_i18n_bundle("weather")
                if bundle and lang in bundle:
                    text = bundle[lang].get(key, key)
                    for k, v in kwargs.items():
                        text = text.replace("{" + k + "}", str(v))
                    return text
                return key
            
            def refresh_weather(self):
                """Refresh weather data"""
                settings = self.plugin.host.get_settings("weather_settings")
                city = settings.get("city", "Moscow")
                units = settings.get("units", "celsius")
                
                # Simulate weather (replace with real API call)
                temp = self.plugin._get_simulated_temp(city)
                if units == "fahrenheit":
                    temp = int(temp * 9/5 + 32)
                    temp_str = f"{temp}℉"
                else:
                    temp_str = f"{temp}℃"
                
                condition_key = self.plugin._get_simulated_condition_key()
                condition = self._t(f"condition_{condition_key}")
                
                self.city_label.setText(f"{self._t('city_label')} {city}")
                self.temp_label.setText(temp_str)
                self.condition_label.setText(condition)
                self.feels_like_label.setText(
                    self._t("feels_like", temp=temp + random.randint(-2, 2))
                )
                self.humidity_label.setText(
                    self._t("humidity", value=random.randint(40, 80))
                )
                
                from datetime import datetime
                now = datetime.now().strftime("%H:%M")
                self.updated_label.setText(self._t("last_updated", time=now))
            
            def _open_settings(self):
                """Open plugin settings"""
                self.plugin.host.open_settings("weather_settings")
        
        return WeatherPageWidget(self, parent)
    
    def _get_simulated_temp(self, city: str) -> int:
        """Simulate temperature based on city (demo)"""
        # In real plugin would call weather API
        base_temps = {
            "moscow": 15, "london": 18, "new york": 22,
            "tokyo": 25, "sydney": 20, "berlin": 17
        }
        return base_temps.get(city.lower(), 20) + random.randint(-3, 3)
    
    def _get_simulated_condition(self) -> str:
        """Get simulated weather condition"""
        conditions = ["sunny", "cloudy", "rainy", "snowy"]
        return random.choice(conditions)
    
    def _get_simulated_condition_key(self) -> str:
        """Get condition key for localization"""
        return self._get_simulated_condition()
    
    def cleanup(self) -> None:
        """Cleanup on plugin unload"""
        pass


# Plugin entry point
def create_plugin(host: PluginHost) -> WeatherPlugin:
    return WeatherPlugin(host)
