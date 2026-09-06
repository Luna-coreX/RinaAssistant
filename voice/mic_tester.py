"""
A wrapper for testing the microphone: starts recording in a background
thread and hands the result to the GUI through a Qt signal.
"""

import threading

from PySide6.QtCore import QObject, Signal

from core.i18n import t as tr
from core.logging_setup import get_logger
from voice import audio_devices


log = get_logger("mic")


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
        # Without finally, an exception in test_microphone left _busy=True
        # forever: the finished signal never came, and the "Check" button
        # stayed grey until the application was restarted.
        result = None
        try:
            result = audio_devices.test_microphone(device_id, seconds=seconds)
        except Exception as e:
            log.exception("Сбой проверки микрофона")
            result = audio_devices.MicTestResult(
                error=tr("Не удалось проверить микрофон: ") + str(e))
        finally:
            self._busy = False
            self.finished.emit(result)
