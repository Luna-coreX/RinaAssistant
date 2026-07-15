"""
Обёртка для теста микрофона: запускает запись в фоновом потоке и
отдаёт результат в GUI через сигнал Qt.
"""

import threading

from PySide6.QtCore import QObject, Signal

from voice import audio_devices


class MicTester(QObject):
    started = Signal()
    finished = Signal(object)  # MicTestResult

    def __init__(self, parent=None):
        super().__init__(parent)
        self._busy = False

    @property
    def available(self):
        return audio_devices.audio_available()

    def run_test(self, device_id="default", seconds=2.0):
        if self._busy:
            return
        self._busy = True
        self.started.emit()
        threading.Thread(target=self._worker, args=(device_id, seconds),
                         daemon=True).start()

    def _worker(self, device_id, seconds):
        result = audio_devices.test_microphone(device_id, seconds=seconds)
        self._busy = False
        self.finished.emit(result)
