from __future__ import annotations
from typing import Dict, Set
import bpy

__all__ = ["evaluate_marker_count"]

def evaluate_marker_count(
    *,
    new_ptrs_after_cleanup: Set[int],
    min_marker: int,
    max_marker: int,
) -> Dict:
    """
    Einfache Band-Prüfung: ENOUGH / TOO_FEW / TOO_MANY
    """
    n = int(len(new_ptrs_after_cleanup))
    if n < int(min_marker):
        return {"status": "TOO_FEW", "count": n, "min": int(min_marker), "max": int(max_marker)}
    if n > int(max_marker):
        return {"status": "TOO_MANY", "count": n, "min": int(min_marker), "max": int(max_marker)}
    return {"status": "ENOUGH", "count": n, "min": int(min_marker), "max": int(max_marker)}
