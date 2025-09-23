# KD-Tree/Grid-Distanzprüfungen
from __future__ import annotations
from typing import List, Tuple, Any
import math

Point = Tuple[float, float]


def build_index(existing_markers: list) -> object:
    """KD-Tree/Grid-Index vorbereiten.
    Erwartet Marker als Dicts mit 'x','y' oder Tupel (x,y).
    Liefert eine einfache Punktliste – für geringe N genügt O(N)."""
    pts: List[Point] = []
    for m in existing_markers or []:
        if isinstance(m, dict):
            try:
                x, y = float(m.get("x", 0.0) if m.get("x", 0.0) is not None else 0.0), float(m.get("y", 0.0) if m.get("y", 0.0) is not None else 0.0)
            except Exception:
                x, y = 0.0, 0.0
        elif isinstance(m, (tuple, list)) and len(m) >= 2:
            try:
                x, y = float(m[0] if m[0] is not None else 0.0), float(m[1] if m[1] is not None else 0.0)
            except Exception:
                x, y = 0.0, 0.0
        else:
            continue
        pts.append((x, y))
    return {"points": pts}


def _dist2(a: Point, b: Point) -> float:
    dx = a[0] - b[0]
    dy = a[1] - b[1]
    return dx * dx + dy * dy


def keep_if_far_enough(candidate, index, min_dist: float) -> bool:
    """True wenn Abstand ≥ min_dist; sonst False."""
    if not index:
        return True
    pts: List[Point] = index.get("points", [])
    if isinstance(candidate, dict):
        try:
            cx = float(candidate.get("x", 0.0) if candidate.get("x", 0.0) is not None else 0.0)
            cy = float(candidate.get("y", 0.0) if candidate.get("y", 0.0) is not None else 0.0)
            c = (cx, cy)
        except Exception:
            c = (0.0, 0.0)
    elif isinstance(candidate, (tuple, list)) and len(candidate) >= 2:
        try:
            c = (float(candidate[0] if candidate[0] is not None else 0.0), float(candidate[1] if candidate[1] is not None else 0.0))
        except Exception:
            c = (0.0, 0.0)
    else:
        return False
    try:
        r2 = float(min_dist) * float(min_dist)
    except Exception:
        r2 = 0.0
    for p in pts:
        if _dist2(c, p) < r2:
            return False
    return True


def feedback_min_distance(current_d: float, n: int, per_stage: int, pattern: int) -> float:
    """d_new = clamp(d * sqrt(n/per_stage), 2*pattern, 3.5*pattern)."""
    d = float(current_d) if current_d else 2.5 * float(pattern)
    ratio = max(0.0001, (float(n) / max(1.0, float(per_stage))))
    d_new = d * math.sqrt(ratio)
    lo = 2.0 * float(pattern)
    hi = 3.5 * float(pattern)
    return max(lo, min(hi, d_new))