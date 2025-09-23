# SPDX-License-Identifier: GPL-2.0-or-later
"""
Helper/strm.py – STRM (Spatio-Temporal Region Map)

- Tiling (z. B. 4x6)
- pro ROI: Texture-Score τ, Motion-Score v, Divergenz φ, Flicker-Proxy, Coverage-Löcher
- Optional: Clustering (DBSCAN/HDBSCAN-Ersatz als Platzhalter)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Tuple

try:
    import bpy  # type: ignore
except Exception:  # pragma: no cover
    bpy = None  # type: ignore


@dataclass
class ROI:
    id: str
    x: int
    y: int
    w: int
    h: int
    tau_tex: float = 0.0
    v_motion: float = 0.0
    phi_div: float = 0.0
    flicker: float = 0.0
    coverage_hole: float = 0.0
    cluster_id: Optional[int] = None
    # Startparameter (werden später gesetzt)
    pattern: int = 0
    alpha: int = 3
    channel: str = "Y"

    def rect(self) -> Tuple[int, int, int, int]:
        return (self.x, self.y, self.w, self.h)


__all__ = ("ROI", "analyze_rois")


def _clip_size(context) -> Tuple[int, int]:
    clip = getattr(context, "edit_movieclip", None)
    if clip is None and bpy is not None:
        try:
            for c in bpy.data.movieclips:
                clip = c
                break
        except Exception:
            pass
    if not clip:
        return (0, 0)
    try:
        return int(clip.size[0]), int(clip.size[1])
    except Exception:
        return (0, 0)


def analyze_rois(context, *, tiles_y: int = 4, tiles_x: int = 6, sample_frames: int = 5) -> List[ROI]:
    """Zerteilt den Clip in tiles_y x tiles_x ROIs und berechnet einfache Heuristiken.
    Platzhalter: Textur-Score tau ~ invers zu lokaler Helligkeitsvarianz (synthetisch),
    Motion-Score v ~ Anteil Track-Bewegung (derzeit 0), Divergenz/Flicker ebenfalls heuristisch 0.
    """
    W, H = _clip_size(context)
    if W <= 0 or H <= 0 or tiles_x <= 0 or tiles_y <= 0:
        return []

    w = max(8, W // tiles_x)
    h = max(8, H // tiles_y)
    rois: List[ROI] = []

    # Grobe Textur-Heuristik: kleinere ROI-Fläche -> eher höherer tau (als Proxy)
    # Später ersetzen durch echten Kanal- und Gradienten-basierten Score.
    for ty in range(tiles_y):
        for tx in range(tiles_x):
            x0 = tx * w
            y0 = ty * h
            roi_id = f"r{ty:02d}_{tx:02d}"
            base_tau = 0.25 + 0.75 * ((tx + 1) * (ty + 1) / float(tiles_x * tiles_y))
            rois.append(ROI(id=roi_id, x=x0, y=y0, w=min(w, W - x0), h=min(h, H - y0), tau_tex=float(base_tau)))

    # TODO: echte Motion/Flicker/Div-Analyse aus korrelierten Markerfeldern ableiten
    # For now: v_motion proportional zur Bildhöhe (reiner Platzhalter)
    for r in rois:
        r.v_motion = 0.0
        r.phi_div = 0.0
        r.flicker = 0.0
        r.coverage_hole = 0.0

    # Optional: Clustering (Platzhalter – alle in Cluster 0)
    for r in rois:
        r.cluster_id = 0

    return rois
