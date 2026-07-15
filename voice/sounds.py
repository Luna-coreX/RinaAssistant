"""
Звуковые эффекты (короткие тоны), генерируются программно — без файлов.

Играются через sounddevice, если он установлен. Уважают настройку
sound_effects и выбранное устройство вывода (output_device). Проигрывание
неблокирующее (в фоне), тихое (не мешает голосу).
"""

import threading


def _enabled(settings):
    return bool(settings.get("sound_effects", True))


def _output_device(settings):
    dev = settings.get("output_device", "default")
    if dev and dev != "default":
        try:
            return int(dev)
        except ValueError:
            return None
    return None


def _play_tone(freqs, duration=0.12, volume=0.25, device=None):
    """Играет последовательность частот (мелодию) в фоне."""
    try:
        import numpy as np
        import sounddevice as sd
    except Exception:
        return

    def worker():
        try:
            sr = 44100
            segments = []
            for f in freqs:
                t = np.linspace(0, duration, int(sr * duration), endpoint=False)
                wave = np.sin(2 * np.pi * f * t)
                # плавное затухание, чтобы не щёлкало
                env = np.linspace(1.0, 0.0, len(wave)) ** 1.5
                segments.append((wave * env).astype("float32"))
            audio = np.concatenate(segments) * volume
            kwargs = {}
            if device is not None:
                kwargs["device"] = device
            sd.play(audio, sr, **kwargs)
            sd.wait()
        except Exception:
            pass

    threading.Thread(target=worker, daemon=True).start()


def play_activation(settings):
    """Звук начала прослушивания (восходящий)."""
    if not _enabled(settings):
        return
    _play_tone([660, 880], duration=0.09, volume=0.25,
               device=_output_device(settings))


def play_response(settings):
    """Звук готового ответа (короткий мягкий)."""
    if not _enabled(settings):
        return
    _play_tone([880, 660], duration=0.08, volume=0.2,
               device=_output_device(settings))


def play_error(settings):
    """Звук ошибки/непонимания (низкий)."""
    if not _enabled(settings):
        return
    _play_tone([300, 240], duration=0.12, volume=0.22,
               device=_output_device(settings))
