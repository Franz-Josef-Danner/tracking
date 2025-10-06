from typing import Final

# Öffentlich genutzter Default (laut Anforderung: int in [1])
default_frames_limit: Final[int] = 1

def resolve_frames_limit(context, fallback: int | None = None) -> int:
    """Ermittelt das effektive Frames-Limit.

    Aktuell nur Rückgabe der Konstante, aber als Funktion gekapselt um später
    auf Scene-/Addon-Properties erweitern zu können.
    """
    if fallback is not None and fallback > 0:
        return fallback
    return default_frames_limit
