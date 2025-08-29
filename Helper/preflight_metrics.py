
from __future__ import annotations
from typing import Iterable, Tuple

__all__ = ["quadrant_coverage"]

def quadrant_coverage(
    coords_px: Iterable[Tuple[float, float]],
    width: float,
    height: float,
    *,
    min_per_quadrant: int = 3
) -> tuple[float, tuple[int, int, int, int]]:
    """
    Bewertet die räumliche Abdeckung der 2D-Punkte.
    - Teilt das Bild in 4 Quadranten (Q1..Q4).
    - Zählt Punkte pro Quadrant.
    - Liefert (coverage_ratio, (n_q1, n_q2, n_q3, n_q4)),
      wobei coverage_ratio = Anteil der Quadranten mit >= min_per_quadrant Punkten.

    Quadranten-Konvention:
      Q1: x>=mx, y<my (oben rechts)
      Q2: x<mx,  y<my (oben links)
      Q3: x<mx,  y>=my (unten links)
      Q4: x>=mx, y>=my (unten rechts)
    """
    try:
        w = float(width) if width else 1.0
        h = float(height) if height else 1.0
    except Exception:
        w, h = 1.0, 1.0

    mx, my = 0.5 * w, 0.5 * h

    n_q1 = n_q2 = n_q3 = n_q4 = 0
    for xy in coords_px or []:
        try:
            x, y = float(xy[0]), float(xy[1])
        except Exception:
            continue
        if x >= mx and y < my:
            n_q1 += 1
        elif x < mx and y < my:
            n_q2 += 1
        elif x < mx and y >= my:
            n_q3 += 1
        else:
            n_q4 += 1

    counts = (n_q1, n_q2, n_q3, n_q4)
    covered = sum(1 for c in counts if c >= int(min_per_quadrant))
    ratio = covered / 4.0
    return ratio, counts
