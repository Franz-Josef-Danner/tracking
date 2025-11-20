"""
Helper/logging_helper.py

Logging wurde vollständig deaktiviert. Die Funktion `tracker_log` ist ein No-Op,
damit bestehende Aufrufer ohne Änderungen weiter funktionieren, aber keinerlei
Ausgaben mehr erzeugt werden.
"""
from typing import Any

def tracker_log(category: str, event: str, message: str, *extra: Any) -> None:
    # Logging ist bewusst deaktiviert (No-Op)
    return
