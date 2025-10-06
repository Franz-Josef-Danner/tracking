"""Helper: Frames-Limit für Tracking-Zyklen.

Dieses Modul definiert eine (vorerst) einfache Konstante `default_frames_limit`,
die angibt, wie viele Frames in einem einzelnen Tracking-Zyklus fortgeschritten
und getrackt werden sollen.

Erweiterbarkeit:
 - Später kann hier z.B. eine Szenen- oder Addon-Property abgefragt werden.
 - Oder Logik für adaptive Schrittweite (z.B. je nach Anzahl aktiv selektierter Marker).

Verwendung:
    from ..Helper.frames_limit import default_frames_limit

    frames_to_track = default_frames_limit  # oder in einer UI-Property gespiegelt

"""

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
