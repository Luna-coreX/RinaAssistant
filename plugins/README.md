# Плагины Rina

Плагин — папка в `plugins/` с `plugin.json` и `main.py` (класс-наследник `Plugin`).

## Манифест plugin.json
```json
{
  "id": "my_plugin",
  "name": "Мой плагин",
  "version": "1.0.0",
  "author": "Имя",
  "description": "Что делает",
  "icon": "🧩",
  "entry": "MyPlugin",
  "api_version": 2
}
```
`api_version` — версия API, которую ожидает плагин (текущая — 2). Если выше
поддерживаемой, плагин не включится и покажет понятную ошибку.

## Хуки (все необязательны)
```python
from plugins.api import Plugin

class MyPlugin(Plugin):
    def on_enable(self): ...
    def on_disable(self): ...
    def on_command(self, text) -> bool: ...   # True = обработано
    def on_event(self, name, data): ...
```

## Сервисы (self.ctx)
- `respond(text)` — Рина озвучит текст и покажет toast (тот же путь, что у ассистента)
- `log(msg)` — лог плагина (виден в карточке)
- `get_setting/set_setting(key, ...)` — свои настройки в конфиге
- `open_window(widget, title)` — показать дополнительное окно
- `notify(title, message)` — уведомление через трей

## Своя ВКЛАДКА в приложении
Переопределите `create_page()` — верните QWidget, и в сайдбаре появится вкладка.
```python
class MyPlugin(Plugin):
    page_title = "Мой раздел"     # как назвать вкладку (иначе имя из манифеста)
    page_icon = "📊"

    def create_page(self):
        from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
        w = QWidget(); v = QVBoxLayout(w)
        v.addWidget(QLabel("Привет из плагина!"))
        return w
```
Вкладка появляется/исчезает при включении/выключении плагина.

## Настройки БЕЗ Qt (декларативно)
Верните `settings_schema()` — приложение само построит панель настроек
(в вашем стиле, с сохранением). Плагину не нужно знать Qt.
```python
from plugins.settings_spec import Toggle, Text, Choice, Slider

class MyPlugin(Plugin):
    def settings_schema(self):
        return [
            Toggle("sound", "Звук", default=True),
            Text("name", "Имя", default="Рина"),
            Choice("mode", "Режим", options=["A", "B", "C"]),
            Slider("count", "Количество", min=1, max=10, default=5),
        ]

    # значения читаются так (с учётом default из схемы):
    def on_enable(self):
        if self.setting("sound"):
            ...
```
Панель настроек показывается на вкладке плагина автоматически.

## Безопасность
Плагин — обычный Python-код с полным доступом. Ошибки изолированы: исключение
в любом хуке ловится, пишется в лог и показывается в карточке — приложение не
падает. Для чужих плагинов помните: доверяйте источнику.

## Примеры в комплекте
- `greeter`, `clock`, `dice` — простые команды.
- `notes` — расширенный: своя вкладка + декларативные настройки + команда «запиши…».
