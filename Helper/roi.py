# STRM/ROI-Analyse & Priorisierung

from __future__ import annotations
from typing import Any, Dict, Tuple, List


BBox = Tuple[int, int, int, int]


def _clip_size(clip: Any) -> Tuple[int, int]:
    try:
        w, h = getattr(clip, "size", (0, 0))
        return int(w or 0), int(h or 0)
    except Exception:
        return 0, 0


def analyze_rois(clip: Any, grid: tuple[int, int] = (4, 6)) -> dict:
    """Return {roi_id: {bbox, texture, motion, divergence, empty_tiles}}.

    Minimal-Implementierung:
    - eine Full-Frame-ROI
    - neutrale Scores, die später durch echte STRM ersetzt werden
    """
    w, h = _clip_size(clip)
    roi: Dict[str, Any] = {
        "bbox": (0, 0, int(w), int(h)),
        "texture": 0.5,
        "motion": 0.5,
        "divergence": 0.0,
        "empty_tiles": [],
        "grid": tuple(int(x) for x in grid),
    }
    return {0: roi}


def cluster_tracks(roi_id, window: int = 30) -> list:
    """Return clusters: [{id, inliers: [track_ids], feats: {...}}].

    Platzhalter: gibt leere Liste zurück. Später per DBSCAN/HDBSCAN ergänzen.
    """
    return []


def prioritize_rois(rois: dict) -> list:
    """Return ROI-Ids in sinnvoller Abarbeitungsreihenfolge.

    Heuristik: sortiere nach (motion + texture) absteigend, dann Flächengröße.
    """
    if not rois:
        return []

    def key(item):
        roi_id, info = item
        tex = float(info.get("texture", 0.0) or 0.0)
        mot = float(info.get("motion", 0.0) or 0.0)
        bbox: BBox = info.get("bbox", (0, 0, 0, 0))
        area = max(1, int(bbox[2]) * int(bbox[3])) if isinstance(bbox, (tuple, list)) and len(bbox) >= 4 else 1
        return (mot + tex, area)

    sorted_items: List[Tuple[int, Dict]] = sorted(rois.items(), key=key, reverse=True)
    return [roi_id for roi_id, _ in sorted_items]