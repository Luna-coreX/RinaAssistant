"""
Sound effects (short tones), generated programmatically — without files.

Played through sounddevice, if it is installed. They respect the
sound_effects setting and the chosen output device (output_device). Playing
is non-blocking (in the background) and quiet (it does not get in the
voice's way).
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
    """Plays a sequence of frequencies (a melody) in the background."""
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
                # a smooth fade, so it does not click
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
    """The sound of listening beginning (rising)."""
    if not _enabled(settings):
        return
    _play_tone([660, 880], duration=0.09, volume=0.25,
               device=_output_device(settings))


def play_response(settings):
    """The sound of an answer being ready (short and soft)."""
    if not _enabled(settings):
        return
    _play_tone([880, 660], duration=0.08, volume=0.2,
               device=_output_device(settings))


def play_error(settings):
    """The sound of an error or of not understanding (low)."""
    if not _enabled(settings):
        return
    _play_tone([300, 240], duration=0.12, volume=0.22,
               device=_output_device(settings))
