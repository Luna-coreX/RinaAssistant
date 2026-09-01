"""
Шина событий ядра — без зависимости от Qt.

Ядро ассистента (распознавание, команды, напоминания) не должно знать про
интерфейс: иначе его нельзя ни запустить отдельно от окна, ни показать в
другой оболочке. Поэтому ядро только публикует события, а кто их слушает —
Qt-адаптер, консоль или процесс на другом языке — его не касается.

Подписчики вызываются в том же потоке, где произошло событие. Ядро работает
в фоновых потоках, поэтому адаптер интерфейса обязан переносить события в
свой поток сам (в Qt это делает сигнал).
"""

import threading

from core.logging_setup import get_logger


log = get_logger("events")


class EventBus:
    def __init__(self):
        self._subs = {}
        self._lock = threading.RLock()

    def on(self, name, callback):
        """Подписаться на событие."""
        with self._lock:
            self._subs.setdefault(name, []).append(callback)
        return callback

    def off(self, name, callback):
        with self._lock:
            handlers = self._subs.get(name)
            if handlers and callback in handlers:
                handlers.remove(callback)

    def clear(self, name=None):
        with self._lock:
            if name is None:
                self._subs.clear()
            else:
                self._subs.pop(name, None)

    def emit(self, name, **payload):
        """
        Отправить событие. Ошибка одного подписчика не должна мешать
        остальным и не должна ронять ядро: событие — уведомление, а не вызов.

        Подписчик принимает полезную нагрузку **одним словарём**:
        `bus.on("speech.recognized", lambda data: ...)`.

        Проглоченная ошибка обязательно пишется в журнал. Раньше здесь стояло
        молчаливое `pass`, и подписчик с неверной сигнатурой падал на каждом
        событии, не оставляя следа: событий просто не было, и это выглядело
        как «шина не работает». Ошибка не мешает остальным, но невидимой быть
        не должна.
        """
        with self._lock:
            handlers = list(self._subs.get(name, ()))
        for handler in handlers:
            try:
                handler(payload)
            except Exception:
                log.exception("Подписчик события %s упал", name)


# Единая шина приложения: ядру нужен способ сообщать о событиях из любого
# модуля, не протаскивая ссылку на движок через все вызовы.
bus = EventBus()
