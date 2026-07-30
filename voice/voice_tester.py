"""
Обёртка для теста голоса: произносит короткую фразу выбранным TTS-движком
в фоновом потоке и отдаёт результат в GUI через сигнал Qt.

Используется на вкладке «Рина», чтобы прослушать выбранный голос/громкость/
скорость до сохранения — синтез блокирующий, поэтому идёт в отдельном потоке.
"""

import threading

from PySide6.QtCore import QObject, Signal

from voice import tts as tts_mod


class VoiceTester(QObject):
    started = Signal()
    finished = Signal(str)   # "" при успехе, иначе текст ошибки

    def __init__(self, parent=None):
        super().__init__(parent)
        self._busy = False

    def run_test(self, engine_id, voice, volume, rate, text):
        if self._busy:
            return
        self._busy = True
        self.started.emit()
        threading.Thread(
            target=self._worker,
            args=(engine_id, voice, volume, rate, text),
            daemon=True,
        ).start()

    def _worker(self, engine_id, voice, volume, rate, text):
        err = ""
        try:
            engine = tts_mod.get_engine(engine_id)
            engine.speak(text, voice=voice, volume=int(volume), rate=int(rate))
        except Exception as e:
            err = str(e)
        finally:
            self._busy = False
            self.finished.emit(err)
