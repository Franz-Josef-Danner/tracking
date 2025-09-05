# SPDX-License-Identifier: GPL-2.0-or-later
"""
Helper/count.py
----------------
Lieferant für per-Track-Fehlerwerte und (optionale) Markeranzahl-Evaluierung.
- error_value(track): robuste Reprojektion-/Fehlermetrik pro Track
- evaluate_marker_count(new_ptrs_after_cleanup=...): simple Bandprüfung
"""
from __future__ import annotations
from typing import Iterable, Dict, Any, Optional, Set, Tuple, List
import math
import statistics
import bpy

__all__ = ("error_value", "evaluate_marker_count")

def error_value(track) -> float:
    """
    Liefert den Reprojektion-/Fehlerwert für *einen* Track.
    Priorität:
      1) track.average_error  (Blender bietet dies häufig an)
      2) track.reprojection_error oder track.error (falls vorhanden)
      3) Mittelwert der marker.reprojection_error
      4) Fallback: 2D-Positionsjitter (px) aus Marker-Koordinaten
    """
    # 1) direkte Track-Attribute (versionstolerant)
    for attr in ("average_error", "reprojection_error", "error"):
        try:
            v = getattr(track, attr, None)
            if v is not None:
                return float(v)
        except Exception:
            pass

    # 2) Marker-basierte Reprojection-Errors
    vals: List[float] = []
    try:
        for m in getattr(track, "markers", []):
            if getattr(m, "mute", False):
                continue
            ev = getattr(m, "reprojection_error", None)
            if ev is not None:
                vals.append(float(ev))
    except Exception:
        vals = []
    if vals:
        try:
            return float(sum(vals) / len(vals))
        except Exception:
            pass

    # 3) Fallback: 2D-Jitter (immer ≥0, gibt Ranking, wenn sonst nichts verfügbar)
    try:
        xs: List[float] = []
        ys: List[float] = []
        for m in getattr(track, "markers", []):
            if getattr(m, "mute", False):
                continue
            co = getattr(m, "co", None)
            if co is not None and len(co) >= 2:
                xs.append(float(co[0]))
                ys.append(float(co[1]))
        if len(xs) >= 2 and len(ys) >= 2:
            return float(statistics.pstdev(xs) + statistics.pstdev(ys))
    except Exception:
        pass
    return 0.0


def evaluate_marker_count(*, new_ptrs_after_cleanup: Optional[Set[int]] = None) -> Dict[str, Any]:
    """
    Prüft die Anzahl neu gesetzter Tracks (Pointer-Set) gegen ein dynamisches Band.
    Bandbreite wird aus Scene-Properties abgeleitet, mit robusten Defaults.
      - marker_adapt: Zielwert (Default 25)
      - marker_min / marker_max (optional, override)
      - marker_min_pct / marker_max_pct (optional, Default 0.8 / 1.2)
    Rückgabe: {"status": "TOO_FEW"/"ENOUGH"/"TOO_MANY", "count": int, "min": int, "max": int}
    """
    scn = bpy.context.scene
    adapt = int(scn.get("marker_adapt", 25))
    min_pct = float(scn.get("marker_min_pct", 0.8))
    max_pct = float(scn.get("marker_max_pct", 1.2))
    mn = int(scn.get("marker_min", max(1, math.floor(adapt * min_pct))))
    mx = int(scn.get("marker_max", max(mn + 1, math.ceil(adapt * max_pct))))
    cnt = int(len(new_ptrs_after_cleanup or set()))
    if cnt < mn:
        st = "TOO_FEW"
    elif cnt > mx:
        st = "TOO_MANY"
    else:
        st = "ENOUGH"
    return {"status": st, "count": cnt, "min": mn, "max": mx}
