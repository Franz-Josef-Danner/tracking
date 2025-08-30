from __future__ import annotations
from typing import Dict, Set, Optional
import bpy

__all__ = ["evaluate_marker_count"]

def evaluate_marker_count(
    *,
    new_ptrs_after_cleanup: Set[int],
    min_marker: Optional[int] = None,
    max_marker: Optional[int] = None,
    context: Optional[bpy.types.Context] = None,
) -> Dict:
    """
    Einfache Band-Prüfung: ENOUGH / TOO_FEW / TOO_MANY

    - Wenn `min_marker` / `max_marker` nicht übergeben werden, werden sie
      automatisch aus der Szene gelesen (Keys/Attribs `marker_min` / `marker_max`),
      die zuvor von `Helper/marker_helper_main.marker_helper_main()` gesetzt wurden.
    - Optional kann ein `context` übergeben werden; ansonsten wird `bpy.context` genutzt.
    """
    # Min/Max dynamisch aus Szene lesen, falls nicht explizit übergeben
    if min_marker is None or max_marker is None:
        scn = (context.scene if context is not None else bpy.context.scene)
        # Unterstützung sowohl für Property-Attribute als auch für ID-Props (Dict)
        resolved_min = getattr(scn, "marker_min", None)
        resolved_max = getattr(scn, "marker_max", None)
        if resolved_min is None:
            resolved_min = scn.get("marker_min", 10)
        if resolved_max is None:
            resolved_max = scn.get("marker_max", 100)
        min_marker = int(resolved_min)
        max_marker = int(resolved_max)

    n = int(len(new_ptrs_after_cleanup))
    if n < int(min_marker):
        return {"status": "TOO_FEW", "count": n, "min": int(min_marker), "max": int(max_marker)}
    if n > int(max_marker):
        return {"status": "TOO_MANY", "count": n, "min": int(min_marker), "max": int(max_marker)}
    return {"status": "ENOUGH", "count": n, "min": int(min_marker), "max": int(max_marker)}
