from __future__ import annotations

"""
Helper/detect.py — Extended feature detection for Blender's Movie Clip Editor.

Highlights
----------
- Backward compatible public API (perform_marker_detection, run_detect_once, run_detect_adaptive)
- Optional ROI post-filter (normalized [0..1] rect or pixel rect)
- KD‑Tree based near‑duplicate removal (faster for many markers)
- Corridor control with smooth PID‑like threshold adaption (stable convergence)
- Selection policy (leave/only_new/restore)
- Duplicate cleanup strategy (delete/mute/tag)
- Optional track tagging prefix for newly created tracks
- Dry‑run mode (executes detect and cleans everything it created)
- Rich result object with metrics
- NEW: Pattern-triplet post step with name aggregation & selection (0.8× / 1.2×)

Blender ≥ 3.0 assumed (mathutils.KDTree available).
"""

import math
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

import bpy
from mathutils.kdtree import KDTree

__all__ = [
    "perform_marker_detection",
    "run_detect_once",
    "run_detect_adaptive",
]

# ---------------------------------------------------------------------
# Scene keys / state
# ---------------------------------------------------------------------
DETECT_LAST_THRESHOLD_KEY = "last_detection_threshold"  # float
_LOCK_KEY = "__detect_lock"
_PREV_SEL_KEY = "__detect_prev_selection"

# ---------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------

@dataclass
class DetectMetrics:
    frame: int
    requested_threshold: float
    applied_threshold: float
    margin_px: int
    min_distance_px: int
    tracks_before: int
    tracks_new_raw: int
    tracks_near_dupe: int
    tracks_new_clean: int
    roi_rejected: int
    duration_ms: float


# ---------------------------------------------------------------------
# Context helpers
# ---------------------------------------------------------------------

def _find_clip_editor_context():
    wm = bpy.context.window_manager
    if not wm:
        return None, None, None, None
    for window in wm.windows:
        screen = window.screen
        if not screen:
            continue
        for area in screen.areas:
            if area.type == "CLIP_EDITOR":
                region = next((r for r in area.regions if r.type == "WINDOW"), None)
                space = area.spaces.active if hasattr(area, "spaces") else None
                if region and space:
                    return window, area, region, space
    return None, None, None, None


def _run_in_clip_context(op_callable, **kwargs):
    window, area, region, space = _find_clip_editor_context()
    if not (window and area and region and space):
        print("[DetectTrace] No CLIP_EDITOR context found – running operator without override.")
        return op_callable(**kwargs)
    override = {
        "window": window,
        "area": area,
        "region": region,
        "space_data": space,
        "scene": bpy.context.scene,
    }
    with bpy.context.temp_override(**override):
        return op_callable(**kwargs)


def _get_movieclip(context: bpy.types.Context) -> Optional[bpy.types.MovieClip]:
    mc = getattr(context, "edit_movieclip", None) or getattr(context.space_data, "clip", None)
    if mc:
        return mc
    for c in bpy.data.movieclips:
        return c
    return None

# ---------------------------------------------------------------------
# Track helpers
# ---------------------------------------------------------------------

def _deselect_all(tracking: bpy.types.MovieTracking) -> None:
    for t in tracking.tracks:
        t.select = False


def _delete_selected_tracks(confirm: bool = True) -> None:
    def _op(**kw):
        return bpy.ops.clip.delete_track(**kw)

    _run_in_clip_context(_op, confirm=confirm)


def _collect_positions_at_frame(
    tracks: Iterable[bpy.types.MovieTrackingTrack], frame: int, w: int, h: int
) -> List[Tuple[float, float]]:
    out: List[Tuple[float, float]] = []
    for t in tracks:
        try:
            m = t.markers.find_frame(frame, exact=True)
        except TypeError:
            m = t.markers.find_frame(frame)
        if m and not getattr(m, "mute", False):
            out.append((m.co[0] * w, m.co[1] * h))
    return out


# ---------------------------------------------------------------------
# Geometry / ROI
# ---------------------------------------------------------------------

def _normalize_roi(
    roi: Optional[Tuple[float, float, float, float]], width: int, height: int
) -> Optional[Tuple[int, int, int, int]]:
    """Return pixel ROI (x, y, w, h) or None. Accepts normalized [0..1] or pixel tuple."""
    if not roi:
        return None
    x, y, w, h = roi
    # Heuristic: values > 1 are pixels
    if max(abs(x), abs(y), abs(w), abs(h)) <= 1.0:
        return (
            int(max(0, round(x * width))),
            int(max(0, round(y * height))),
            int(max(1, round(w * width))),
            int(max(1, round(h * height))),
        )
    return (int(x), int(y), int(w), int(h))


def _inside_roi(px: float, py: float, roi_px: Tuple[int, int, int, int]) -> bool:
    x, y, w, h = roi_px
    return (x <= px <= x + w) and (y <= py <= y + h)


# ---------------------------------------------------------------------
# Core ops
# ---------------------------------------------------------------------

def _scaled_params(threshold: float, margin_base: int, min_distance_base: int) -> Tuple[int, int]:
    factor = math.log10(max(float(threshold), 1e-6) * 1e6) / 6.0
    margin = max(1, int(int(margin_base) * factor))
    min_distance = max(1, int(int(min_distance_base) * factor))
    return margin, min_distance


def perform_marker_detection(
    clip: bpy.types.MovieClip,
    tracking: bpy.types.MovieTracking,
    threshold: float,
    margin_base: int,
    min_distance_base: int,
) -> int:
    margin, min_distance = _scaled_params(float(threshold), int(margin_base), int(min_distance_base))

    def _op(**kw):
        try:
            return bpy.ops.clip.detect_features(**kw)
        except TypeError:
            return bpy.ops.clip.detect_features()

    print(
        f"[DetectTrace] detect_features: thr={threshold:.6f}, margin={margin}, min_dist={min_distance}"
    )
    t0 = time.perf_counter()
    try:
        _run_in_clip_context(
            _op,
            margin=int(margin),
            min_distance=int(min_distance),
            threshold=float(threshold),
        )
    except Exception as ex:
        dt = (time.perf_counter() - t0) * 1000.0
        print(f"[DetectError] detect_features Exception ({dt:.1f} ms): {ex}")
        raise
    dt = (time.perf_counter() - t0) * 1000.0
    print(f"[DetectTrace] detect_features DONE in {dt:.1f} ms")
    return sum(1 for t in tracking.tracks if getattr(t, "select", False))

# ---------------------------------------------------------------------
# Pattern-triplet helpers & API
# ---------------------------------------------------------------------
# (… Rest des Codes bleibt unverändert …)
