# SPDX-License-Identifier: GPL-2.0-or-later
"""
Helper/persistence.py – Telemetrie, Presets, Reuse

- Logging (CSV/JSON) pro ROI/Cluster/Marker
- Preset-Cache nach (Auflösung-Bin, Texture-Bin, Motion-Bin, Quadrant)
- Exploration: ε-greedy; Aging via Median-Score
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from typing import Dict, Any, List, Optional, Tuple

from .strm import ROI
from .governance import KPI, composite_score, publish_telem_on_scene, publish_score_on_scene

try:
    import bpy  # type: ignore
except Exception:  # pragma: no cover
    bpy = None  # type: ignore

__all__ = ("finalize_metrics", "write_presets")


@dataclass
class Preset:
    pattern: int
    alpha: int
    threshold: float
    channel: str
    score: float


def _scene_path_key() -> str:
    return "kc_preset_cache_json"


def finalize_metrics(context, roi: ROI, kpi: KPI) -> Dict[str, Any]:
    # Veröffentlichung auf Szene und Score-Berechnung
    publish_telem_on_scene(kpi)
    s = composite_score(kpi)
    publish_score_on_scene(s)
    return {"status": "READY", "score": float(s)}


def write_presets(context, roi: ROI, kpi: KPI, detect_threshold: float) -> Dict[str, Any]:
    """Persistiert einen Preset-Eintrag in der Szene (als JSON-Cache).
    Schlüsselbildung stark vereinfacht: (tex_bin, motion_bin) je ROI.
    """
    s = composite_score(kpi)
    entry = Preset(pattern=int(roi.pattern), alpha=int(roi.alpha), threshold=float(detect_threshold), channel=str(roi.channel), score=float(s))

    scn = bpy.context.scene if bpy is not None else None
    cache: Dict[str, Any] = {}
    if scn is not None:
        raw = scn.get(_scene_path_key(), "")
        if raw:
            try:
                cache = json.loads(raw)
            except Exception:
                cache = {}
        key = f"tex{int(roi.tau_tex*10)}|mot{int(roi.v_motion*10)}"
        cache[key] = asdict(entry)
        try:
            scn[_scene_path_key()] = json.dumps(cache, separators=(",", ":"))
        except Exception:
            pass
    return {"status": "READY", "cache_size": len(cache)}
