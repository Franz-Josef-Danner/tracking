# Helper/logging_helper.py
"""Zentrales Logging für den Tracker.

Minimalistisch und schnell: schreibt kompakte Zeilen in stdout, damit
Ausgaben in Blender/Terminal sichtbar sind. Bei Bedarf kann Logging
über `set_tracker_logging(False)` deaktiviert werden.
"""
from typing import Any

_DEF_PREFIX = "[TRACK]"
_ENABLE_LOGGING = True

def set_tracker_logging(enabled: bool) -> None:
    global _ENABLE_LOGGING
    _ENABLE_LOGGING = bool(enabled)

def tracker_log(category: str, event: str, message: str, *extra: Any) -> None:
    if not _ENABLE_LOGGING:
        return
    try:
        if extra:
            msg = f"{_DEF_PREFIX}[{category}][{event}] {message} | " + " ".join(str(e) for e in extra)
        else:
            msg = f"{_DEF_PREFIX}[{category}][{event}] {message}"
        print(msg)
    except Exception:
        # Keine Exceptions aus dem Logger nach außen geben
        pass
