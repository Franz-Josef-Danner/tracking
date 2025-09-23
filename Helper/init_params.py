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


def enforce_limits(pattern: int, alpha: int, width: int, height: int) -> tuple[int, int, int]:
    """Clamp pattern∈[9..41], alpha∈[2..4], search≤0.12*min_dim."""
    p = max(9, min(41, int(pattern)))
    a = max(2, min(4, int(alpha)))
    search = _round_even(a * p)
    max_search = int(0.12 * min(width, height)) if width and height else search
    if max_search > 0:
        search = min(search, max_search)
    return p, a, search


def init_pattern_search(width: int, height: int, motion_score: float = 0.5) -> tuple[int, int, int]:
    """Return (pattern, alpha, search); search=round_even(alpha*pattern), Limits greifen.

    p0: round_odd(diag/150) → clamp 9..41
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