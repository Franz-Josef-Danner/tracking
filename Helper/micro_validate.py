# 10f-Micro-Tracking-Checks (Corr/Residual/Jump)
from __future__ import annotations
from typing import List, Dict


def validate_markers(markers: list, frames: int = 10, corr_min: float = 0.60, jump_guard: bool = True) -> list:
    """Track kurz; filtere schlechte Kandidaten; return gefilterte Liste.
    In dieser minimalen Implementierung nutzen wir vorhandene Felder an den Marker-Dicts:
      - 'corr': Korrelation (0..1)
      - 'jump_spike': bool
      - 'residual': Fehlermaß (px)
    Fehlen Felder, werden Kandidaten konservativ akzeptiert.
    """
    if not markers:
        return []
    out = []
    for m in markers:
        corr = float(m.get("corr", 1.0)) if isinstance(m, dict) else 1.0
        jump = bool(m.get("jump_spike", False)) if isinstance(m, dict) else False
        if corr < corr_min:
            continue
        if jump_guard and jump:
            continue
        out.append(m)
    return out


def trim_to_band(markers: list, target_hi: int) -> list:
    """Nach Qualität (corr, residual) & Diversität (nn_distance) ausdünnen.
    Sortierreihenfolge: hohe corr, niedrige residual, hohe nn_distance.
    """
    if not markers:
        return []
    if target_hi <= 0:
        return []

    def key(m: Dict):
        corr = float(m.get("corr", 1.0))
        resid = float(m.get("residual", 0.0))
        nn = float(m.get("nn_distance", 1e9))
        return (corr, -resid, nn)

    sorted_ms = sorted(markers, key=key, reverse=True)
    return sorted_ms[: int(target_hi)]