# SPDX-License-Identifier: GPL-2.0-or-later
"""
Helper/models_select.py – Motion-Model-Selektion (Cluster-basiert)

RANSAC-Fit-Platzhalter + Komplexitätsstrafe. Promotion-/Rollback-Hysterese
werden aktuell nur schematisch umgesetzt.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Any, List

from .strm import ROI

__all__ = ("cluster_fit_models", "select_apply_motion_models")

try:
    import bpy  # type: ignore
except Exception:  # pragma: no cover
    bpy = None  # type: ignore


@dataclass
class ModelFit:
    model: str
    rms: float
    inliers: int
    outliers: int


def cluster_fit_models(context, roi: ROI, window: int = 30) -> List[ModelFit]:
    # Platzhalter: liefert feste Reihung
    return [
        ModelFit("Loc", 1.0, 30, 5),
        ModelFit("LocRot", 0.9, 28, 6),
        ModelFit("LocRotScale", 0.85, 26, 7),
    ]


def select_apply_motion_models(context, roi: ROI, fits: List[ModelFit], feats: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Wählt anhand S = RMS + λ·κ das beste Modell und setzt es im Tracking-Settings-Default
    oder für selektierte Tracks.
    """
    if not fits:
        return {"status": "NO_FITS"}

    # κ Gewichte (1,2,3,4,6)
    K = {"Loc": 1, "LocRot": 2, "LocRotScale": 3, "Affine": 4, "Perspective": 6}
    lam = 0.12

    best = min(fits, key=lambda f: float(f.rms) + lam * float(K.get(f.model, 6)))

    if bpy is not None:
        clip = getattr(context, "edit_movieclip", None)
        if clip:
            try:
                clip.tracking.settings.default_motion_model = best.model
            except Exception:
                pass
    return {"status": "READY", "chosen": best.model, "score": float(best.rms + lam * K.get(best.model, 6))}
