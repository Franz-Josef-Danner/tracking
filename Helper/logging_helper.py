# Helper/logging_helper.py
"""Zentrales Logging – aktuell vollständig stummgeschaltet (No-Op).
Alle Aufrufer können `tracker_log(...)` weiterhin bedenkenlos verwenden,
die Funktion erzeugt jedoch keine Ausgabe mehr.
"""
from typing import Any

_DEF_PREFIX = "[TRACK]"

def tracker_log(category: str, event: str, message: str, *extra: Any) -> None:
    """No-Op: Unterdrückt sämtliche Log-Ausgaben dauerhaft."""
    return
