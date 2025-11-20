# Helper/logging_helper.py
"""Zentrales, leichtgewichtiges Logging für Tracker-Operatoren.
Verwendet bewusst nur print, damit es auch in Blender-Konsole sichtbar ist.
"""
from typing import Any

_DEF_PREFIX = "[TRACK]"

def tracker_log(category: str, event: str, message: str, *extra: Any) -> None:
    """Einheitliches Log-Format.
    Beispiel: tracker_log("CALIBRATE", "STORE", "Stored 5 tracks")
    Ausgabe:  [TRACK][CALIBRATE][STORE] Stored 5 tracks
    """
    try:
        tail = " " + " ".join(str(e) for e in extra) if extra else ""
        print(f"{_DEF_PREFIX}[{category}][{event}] {message}{tail}")
    except Exception:
        # Logging soll niemals Fehler propagieren
        pass
