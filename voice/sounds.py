"""
Sound effects (short tones), generated programmatically — without files.

Played through sounddevice, if it is installed. They respect the
sound_effects setting and the chosen output device (output_device). Playing
is non-blocking (in the background) and quiet (it does not get in the
voice's way).
"""

import atexit
import threading

#: Tones being played right now. Kept so that the process can wait for
#: them instead of being torn down on top of them — see `_hush`.
_SOUNDING = set()

#: One tone at a time.
#:
#: `sounddevice` plays through one default stream, and `sd.play` from
#: two threads at once takes that stream apart from both ends. Windows
#: answers with `0xC0000374` — a corrupted heap — and it answers at some
#: later moment, so the report points anywhere but here. Found when the
#: checks moved onto the interpreter the core runs on: a test that
#: answers twenty-seven times plays twenty-seven cues, and some of them
#: overlap.
#:
#: Two cues of a tenth of a second each do not need to sound together —
#: one after the other is what a person hears anyway.
_ONE_AT_A_TIME = threading.Lock()


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


@atexit.register
def _hush():
    """
    Stop the tones before the process is taken apart.

    **A daemon thread inside a native library is killed where it
    stands.** The tone plays in a thread of its own and sits inside
    PortAudio while it sounds; when the process ends at that moment,
    Python kills the thread mid-call and Windows answers with an access
    violation. Measured: two runs in three of `test_router.py` ended
    with `0xC0000005` and no Python frame anywhere in the report — and
    all the checks had already passed. A program that answers everything
    correctly and then falls over on the way out is still a program that
    falls over.

    It did not show until the checks were moved onto the interpreter the
    core actually runs on: `sounddevice` is installed there and not in
    the system one, so `_play_tone` used to return at the import and
    play nothing at all.

    `atexit` runs while the daemon threads are still alive, which is
    exactly the moment when there is still somebody to stop.
    """
    try:
        import sounddevice as sd
    except Exception:                                   # noqa: BLE001
        return
    try:
        sd.stop()
    except Exception:                                   # noqa: BLE001
        pass
    for thread in list(_SOUNDING):
        thread.join(timeout=0.5)


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
            with _ONE_AT_A_TIME:
                sd.play(audio, sr, **kwargs)
                sd.wait()
        except Exception:
            pass
        finally:
            _SOUNDING.discard(threading.current_thread())

    sounding = threading.Thread(target=worker, name="rina-tone", daemon=True)
    _SOUNDING.add(sounding)
    sounding.start()


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
