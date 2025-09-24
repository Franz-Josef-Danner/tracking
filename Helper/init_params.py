# Startwerte (pattern/search, alpha), Limit
from __future__ import annotations
import math
from typing import Tuple


def _round_odd(x: float) -> int:
    n = int(round(x))
    return n if n % 2 == 1 else (n + 1)


def _round_even(x: float) -> int:
    n = int(round(x))
    return n if n % 2 == 0 else (n + 1)


def _default_max_pattern(width: int, height: int) -> int:
    """Dynamische Obergrenze für pattern in px, je nach Auflösung.
    Ziel: Für High-Res > 2.5K größere Pattern erlauben (z. B. bis 61/71/81).
    """
    min_dim = max(0, int(min(width or 0, height or 0)))
    # Schwellen: konservativ staffeln
    if min_dim <= 1200:
        return 41
    if min_dim <= 2000:
        return 51
    if min_dim <= 3000:
        return 61
    if min_dim <= 4000:
        return 71
    return 81


def enforce_limits(pattern: int, alpha: int, width: int, height: int, max_pattern: int | None = None) -> tuple[int, int, int]:
    """Clamp pattern∈[9..max_pattern], alpha∈[2..4], search≤0.12*min_dim.
    max_pattern ist optional; ohne Angabe wird eine dynamische Grenze aus der Auflösung abgeleitet.
    """
    cap = int(max_pattern) if (isinstance(max_pattern, int) and max_pattern >= 9) else _default_max_pattern(width, height)
    p = max(9, min(int(cap), int(pattern)))
    a = max(2, min(4, int(alpha)))
    search = _round_even(a * p)
    max_search = int(0.12 * min(width, height)) if width and height else search
    if max_search > 0:
        search = min(search, max_search)
    return p, a, search


def init_pattern_search(width: int, height: int, motion_score: float = 0.5) -> tuple[int, int, int]:
    """Return (pattern, alpha, search); search=round_even(alpha*pattern), Limits greifen.

    p0: round_odd(diag/150) → clamp 9..max_pattern (dynamisch)
    α default 3; α↑ bei hoher Motion (>=0.75), α↓ bei stabil (<=0.25)
    search0 = round_even(α·p0), Limit ≤ 0.12·min(width,height)
    """
    diag = math.hypot(max(1, width), max(1, height))
    p0 = _round_odd(diag / 150.0)
    # Alpha auf Basis der Bewegung leicht anpassen
    if motion_score >= 0.75:
        a0 = 4
    elif motion_score <= 0.25:
        a0 = 2
    else:
        a0 = 3
    return enforce_limits(p0, a0, width, height)