# Helper/logging_helper.py
"""Zentrales Logging für Tracking-Helfer.

Konfiguration (Umgebungsvariablen oder Laufzeit-Funktionen):
  TRACKER_LOG=1                 -> Logging aktivieren (alles)
  TRACKER_LOG_FILTER=cat1,cat2  -> Nur angegebene Kategorien erlauben
  TRACKER_LOG_EVENT_FILTER=e1,e2-> Events filtern (UND mit Kategorie-Filter)

Zur Laufzeit im Blender-Python:
  from Helper.logging_helper import set_tracker_log_enabled, set_tracker_log_filters
  set_tracker_log_enabled(True)
  set_tracker_log_filters(categories=["MOTION"], events=["BACKWARD"])

Alle Aufrufer verwenden weiterhin `tracker_log(category, event, message, *extra)`.
"""
from __future__ import annotations
from typing import Any, Iterable
import os
import sys
import threading

_DEF_PREFIX = "[TRACK]"
_lock = threading.Lock()

_LOG_ENABLED = os.getenv("TRACKER_LOG", "0").lower() in {"1", "true", "yes", "on"}

def _split_env_list(value: str | None) -> list[str]:
    if not value:
        return []
    return [v.strip() for v in value.split(",") if v.strip()]

_CATEGORY_FILTER = _split_env_list(os.getenv("TRACKER_LOG_FILTER"))
_EVENT_FILTER = _split_env_list(os.getenv("TRACKER_LOG_EVENT_FILTER"))

def set_tracker_log_enabled(enabled: bool) -> None:
    global _LOG_ENABLED
    _LOG_ENABLED = bool(enabled)

def set_tracker_log_filters(categories: Iterable[str] | None = None,
                            events: Iterable[str] | None = None) -> None:
    global _CATEGORY_FILTER, _EVENT_FILTER
    _CATEGORY_FILTER = [c.strip() for c in (categories or []) if c and c.strip()]
    _EVENT_FILTER = [e.strip() for e in (events or []) if e and e.strip()]

def tracker_log(category: str, event: str, message: str, *extra: Any) -> None:
    if not _LOG_ENABLED:
        return
    if _CATEGORY_FILTER and category not in _CATEGORY_FILTER:
        return
    if _EVENT_FILTER and event not in _EVENT_FILTER:
        return
    try:
        with _lock:
            parts = [_DEF_PREFIX, category, event, message]
            if extra:
                parts.append(" ".join(str(e) for e in extra))
            sys.stdout.write(" | ".join(parts) + "\n")
    except Exception:
        # Fallback: keine Exception nach außen
        pass
