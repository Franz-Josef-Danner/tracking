# STRM/ROI-Analyse & Priorisierung

from typing import Any

def analyze_rois(clip: Any, grid: tuple[int, int] = (4, 6)) -> dict:
    """Return {roi_id: {bbox, texture, motion, divergence, empty_tiles}}."""
    raise NotImplementedError


def cluster_tracks(roi_id, window: int = 30) -> list:
    """Return clusters: [{id, inliers: [track_ids], feats: {...}}]."""
    raise NotImplementedError


def prioritize_rois(rois: dict) -> list:
    """Return ROI-Ids in sinnvoller Abarbeitungsreihenfolge."""
    raise NotImplementedError