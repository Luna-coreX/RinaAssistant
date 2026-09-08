"""
Audio devices: enumerating microphones/speakers and testing the microphone.

Like the rest of the voice layer, it works over optional libraries:
  - sounddevice (+ numpy) — preferred: the list of input/output devices and
    recording for a microphone test with a level measurement;
  - pyaudio — a fallback for enumeration;
  - if nothing is installed — we return "The default device" and honestly
    report that the test is unavailable.

Recording from the microphone blocks, so the test is started from a
background thread (see its use in the UI). Here there are only the "raw"
functions.
"""


from core.i18n import t as tr


def _try_sounddevice():
    try:
        import sounddevice as sd  # noqa
        import numpy as np        # noqa
        return sd, np
    except Exception:
        return None, None


def _try_pyaudio():
    try:
        import pyaudio  # noqa
        return pyaudio
    except Exception:
        return None


DEFAULT_DEVICE = ("default", "Устройство по умолчанию")


def input_devices():
    """A list of (device_id, label) of INPUT devices (microphones)."""
    sd, _ = _try_sounddevice()
    result = [DEFAULT_DEVICE]
    if sd is not None:
        try:
            for idx, dev in enumerate(sd.query_devices()):
                if dev.get("max_input_channels", 0) > 0:
                    result.append((str(idx), dev.get("name", tr("Вход {idx}", idx=idx))))
            return result
        except Exception:
            pass
    pa = _try_pyaudio()
    if pa is not None:
        try:
            p = pa.PyAudio()
            for i in range(p.get_device_count()):
                info = p.get_device_info_by_index(i)
                if info.get("maxInputChannels", 0) > 0:
                    result.append((str(i), info.get("name", tr("Вход {i}", i=i))))
            p.terminate()
        except Exception:
            pass
    return result


def output_devices():
    """A list of (device_id, label) of OUTPUT devices (speakers/headphones)."""
    sd, _ = _try_sounddevice()
    result = [DEFAULT_DEVICE]
    if sd is not None:
        try:
            for idx, dev in enumerate(sd.query_devices()):
                if dev.get("max_output_channels", 0) > 0:
                    result.append((str(idx), dev.get("name", tr("Выход {idx}", idx=idx))))
            return result
        except Exception:
            pass
    pa = _try_pyaudio()
    if pa is not None:
        try:
            p = pa.PyAudio()
            for i in range(p.get_device_count()):
                info = p.get_device_info_by_index(i)
                if info.get("maxOutputChannels", 0) > 0:
                    result.append((str(i), info.get("name", tr("Выход {i}", i=i))))
            p.terminate()
        except Exception:
            pass
    return result


def audio_available():
    """Is recording available for a microphone test."""
    sd, _ = _try_sounddevice()
    return sd is not None


class MicTestResult:
    def __init__(self, ok=False, level=0.0, peak=0.0, error=None):
        self.ok = ok
        self.level = level   # the mean RMS level, 0..1
        self.peak = peak     # the peak level, 0..1
        self.error = error


def test_microphone(device_id="default", seconds=2.0, samplerate=16000):
    """
    Blockingly records a short fragment from the microphone and returns the
    level. Call from a background thread.
    """
    sd, np = _try_sounddevice()
    if sd is None:
        return MicTestResult(error="Нужен пакет sounddevice (+ numpy) для теста.")

    try:
        kwargs = {"samplerate": samplerate, "channels": 1, "dtype": "float32"}
        if device_id and device_id != "default":
            try:
                kwargs["device"] = int(device_id)
            except ValueError:
                pass
        frames = int(seconds * samplerate)
        recording = sd.rec(frames, **kwargs)
        sd.wait()
        data = recording.flatten()
        if len(data) == 0:
            return MicTestResult(error="Пустая запись")
        rms = float(np.sqrt(np.mean(np.square(data))))
        peak = float(np.max(np.abs(data)))
        # we normalise into a convenient 0..1 range (speech rarely gives rms > 0.3)
        level = min(1.0, rms * 3.0)
        return MicTestResult(ok=True, level=level, peak=min(1.0, peak))
    except Exception as e:
        return MicTestResult(error=f"Ошибка записи: {e}")
