# Clean-Error, Short-Segments, Gap-Handling
from __future__ import annotations
from typing import Dict, Any


def periodic_cleanup(roi_id, clean_error_px: float, min_len: int) -> Dict[str, Any]:
    """clean_error_tracks, clean_short_segments, Gap-Fixes mit leichten Defaults.
    Platzhalter: gibt einen simplen Report zurück.
    """
    return {
        "roi_id": roi_id,
        "clean_error_px": float(clean_error_px),
        "min_len": int(min_len),
        "removed_error_tracks": 0,
        "trimmed_segments": 0,
        "gaps_fixed": 0,
    }


def refine_on_fail(roi_id, top_k: int = 10) -> Dict[str, Any]:
    """Eskalation bei hartnäckigen Fails: refine_high_error(top_k) + Reset auf Find-Low.
    Platzhalter: gibt nur eine leere Zusammenfassung zurück.
    """
    return {"refined": 0, "reset": 0, "top_k": int(top_k)}