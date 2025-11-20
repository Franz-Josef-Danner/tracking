# Helper/logging_helper.py
"""Einfaches Logging: direkte print-Ausgabe in Blender-Konsole.

Kein Filter, keine Umgebungsvariablen, keine Spielereien.
Alle Aufrufer nutzen weiterhin `tracker_log(category, event, message, *extra)`.
"""
from typing import Any

_DEF_PREFIX = "[TRACK]"

def tracker_log(category: str, event: str, message: str, *extra: Any) -> None:
    if extra:
        print(f"{_DEF_PREFIX}|{category}|{event}|{message}", *extra)
    else:
        print(f"{_DEF_PREFIX}|{category}|{event}|{message}")
