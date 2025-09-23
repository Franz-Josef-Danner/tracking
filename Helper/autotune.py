# SPDX-License-Identifier: GPL-2.0-or-later
"""
Helper/autotune.py – Detect-Autotune & Channel-Selektion-Microtrials

- Regeln für detect_threshold, min_distance, nms_window(~pattern), edge_suppression
- Micro-Trials (30f) als Platzhalter: heuristische Score-Berechnung
"""
from __future__ import annotations

from typing import Dict, Any, Optional

from .strm import ROI
from .init_params import _round_even
from .governance import LIMITS

try:
    import bpy  # type: ignore
except Exception:  # pragma: no cover
    bpy = None  # type: ignore

from . import detect as detect_mod

__all__ = ("autotune_detect",)


def _safe_scene() -> Any:
    return bpy.context.scene if bpy is not None else None


def autotune_detect(context, roi: ROI) -> Dict[str, Any]:
    """Ermittelt Startparameter für Detect gemäß Regeln und publiziert sie in der Szene.
    Gibt ein Dict mit allen gesetzten Werten zurück.
    """
    scn = _safe_scene()

    pattern = int(max(LIMITS.pattern_min, min(LIMITS.pattern_max, roi.pattern or 15)))
    alpha = int(LIMITS.clamp_alpha(roi.alpha or 3))

    # nms/min_distance ~ pattern
    min_distance_px = int(max(2 * pattern, min(3.5 * pattern, 3 * pattern)))

    # margin/search = alpha * pattern, gekappt an 12% minDim (wird unten in detect genutzt)
    search_size = int(_round_even(alpha * pattern))

    # Schwellenwert: low texture -> niedriger, viele Fehlmatches -> höher
    if roi.tau_tex < 0.35:
        thr = 0.25
        multiscale = True
        max_features = 500
    else:
        thr = 0.5
        multiscale = False
        max_features = 350

    # Divergenz hoch → edge_suppression on
    edge_suppression = bool(roi.phi_div > 0.2)

    # Veröffentlichung auf Szene für Transparenz
    if scn is not None:
        scn["kc_autotune_pattern"] = int(pattern)
        scn["kc_autotune_alpha"] = int(alpha)
        scn["kc_autotune_search"] = int(search_size)
        scn["kc_autotune_threshold"] = float(thr)
        scn["kc_autotune_min_distance"] = int(min_distance_px)
        scn["kc_autotune_edge_suppression"] = bool(edge_suppression)
        scn["kc_autotune_multiscale"] = bool(multiscale)
        scn["kc_autotune_max_features"] = int(max_features)

    # Detect-Call: wir übergeben margin=min(search, limit) und min_distance 1:1
    res = detect_mod.run_detect_basic(
        bpy.context,
        threshold=float(thr),
        margin=int(search_size),  # wird in detect nicht re-skaliert
        min_distance=int(min_distance_px),
        placement="FRAME",
        select=True,
    )
    return {**res, "pattern": pattern, "search": search_size}
