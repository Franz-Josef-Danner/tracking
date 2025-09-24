# Clean-Error, Short-Segments, Gap-Handling
from __future__ import annotations
from typing import Dict, Any


def periodic_cleanup(roi_id, clean_error_px: float, min_len: int) -> None:
    """clean_error_tracks, clean_short_segments, Gap-Fixes mit leichten Defaults.
    Platzhalter: keine Operation, nur Schnittstelle bereitstellen.
    """
    return None


def refine_on_fail(roi_id, top_k: int = 10) -> Dict[str, Any]:
    """Eskalation bei hartnäckigen Fails: refine_high_error(top_k) + Reset auf Find-Low.
    Platzhalter: gibt nur eine leere Zusammenfassung zurück.
    """
    return {"refined": 0, "reset": 0, "top_k": int(top_k)}