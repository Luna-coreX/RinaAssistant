"""
Небольшая шина сигналов приложения — чтобы страницы могли
уведомлять главное окно (и наоборот) без прямых ссылок друг на друга.
"""

from PySide6.QtCore import QObject, Signal


class _AppSignals(QObject):
    # настройка сворачивания в трей изменилась
    tray_pref_changed = Signal()

    # пользователь изменил горячую клавишу -> перерегистрировать
    hotkey_changed = Signal()

    # окно сообщает, доступен ли глобальный хоткей (bool) — для подсказки в UI
    hotkey_status = Signal(bool)

    # тумблер «всегда слушать» на странице Рины изменился
    always_listen_changed = Signal(bool)

    # список пользовательских команд изменился (создали/удалили/изменили)
    commands_changed = Signal()

    # запрос выполнить пользовательскую команду по id (кнопка «Выполнить»)
    run_command = Signal(str)

    # в историю добавилась запись
    history_changed = Signal()

    # язык интерфейса изменился — пересобрать UI
    language_changed = Signal()

    # программу запустить не удалось — предложить указать файл вручную
    app_not_found = Signal(str)      # что искали

    # список таймеров/напоминаний изменился — обновить вкладку
    reminders_changed = Signal()

    # действие над окном Рины (свернуть/показать/выйти/озвучка).
    # Нужен именно сигнал: команды выполняются в фоновом потоке распознавания,
    # а трогать виджеты можно только из GUI-потока.
    window_action = Signal(str)      # id действия

    def __init__(self):
        super().__init__()
        self.last_hotkey_global = False  # кэш последнего статуса для UI

    def _remember_status(self, ok):
        self.last_hotkey_global = ok


app_signals = _AppSignals()
app_signals.hotkey_status.connect(app_signals._remember_status)
