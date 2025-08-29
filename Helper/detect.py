# SPDX-License-Identifier: GPL-2.0-or-later
from __future__ import annotations

import math
from typing import Any, Dict, Optional, Set, Tuple

import bpy

__all__ = [
    "perform_marker_detection",
    "run_detect_basic",  # Kern: Marker setzen + Baseline
    "run_detect_once",   # Thin-Wrapper für Backward-Compat
]

# ---------------------------------------------------------------------
# Scene keys / state
# ---------------------------------------------------------------------
DETECT_LAST_THRESHOLD_KEY = "last_detection_threshold"  # float
_LOCK_KEY = "__detect_lock"

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

# ---------------------------------------------------------------------
# Core ops
# ---------------------------------------------------------------------
def _scaled_params(threshold: float, margin_base: int, min_distance_base: int) -> Tuple[int, int]:
    # Stabil: skaliert Margin/MinDistance moderat mit der Korrelation
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

    _run_in_clip_context(
        _op,
        margin=int(margin),
        min_distance=int(min_distance),
        threshold=float(threshold),
    )
    return sum(1 for t in tracking.tracks if getattr(t, "select", False))

# ---------------------------------------------------------------------
# Public: basic detect (Marker setzen + Baseline zurückgeben)
# ---------------------------------------------------------------------
def run_detect_basic(
    context: bpy.types.Context,
    *,
    start_frame: Optional[int] = None,
    threshold: Optional[float] = None,
    margin_base: Optional[int] = None,
    min_distance_base: Optional[int] = None,
    selection_policy: str = "only_new",  # "only_new" | "leave"
) -> Dict[str, Any]:
    """Setzt Marker (detect_features) mit skalierten Parametern.
    Selektiert optional nur NEUE Marker und liefert Baseline (pre_ptrs, frame, width, height).
    KEIN Cleanup, KEINE Distanz-Logik, KEINE Triplets.
    """
    scn = context.scene
    clip = _get_movieclip(context)
    if not clip:
        return {"status": "FAILED", "reason": "no_movieclip"}

    tracking = clip.tracking
    width, height = int(clip.size[0]), int(clip.size[1])

    if start_frame is not None:
        try:
            scn.frame_set(int(start_frame))
        except Exception:
            pass
    frame = int(scn.frame_current)

    # Threshold aus Szene, falls nicht explizit gesetzt
    if threshold is None:
        base_thr = float(getattr(tracking.settings, "default_correlation_min", 0.75))
        try:
            last_thr = float(scn.get(DETECT_LAST_THRESHOLD_KEY, base_thr))
        except Exception:
            last_thr = base_thr
        threshold = max(1e-6, float(last_thr))
    else:
        threshold = max(1e-6, float(threshold))

    # Basisskalen
    if margin_base is None:
        margin_base = max(1, int(width * 0.025))
    if min_distance_base is None:
        min_distance_base = max(1, int(width * 0.05))

    # Vorherige Pointer sichern (Baseline)
    pre_ptrs: Set[int] = {t.as_pointer() for t in tracking.tracks}

    # Detect ausführen
    _deselect_all(tracking)
    try:
        perform_marker_detection(
            clip, tracking, float(threshold), int(margin_base), int(min_distance_base)
        )
    except Exception:
        return {"status": "FAILED", "reason": "detect_features_failed", "frame": int(frame)}

    # Nur NEUE markieren (keine weitere Logik)
    new = [t for t in tracking.tracks if t.as_pointer() not in pre_ptrs]
    _deselect_all(tracking)
    if selection_policy == "only_new":
        for t in new:
            t.select = True

    # Schwelle persistieren (für den nächsten Pass)
    try:
        scn[DETECT_LAST_THRESHOLD_KEY] = float(threshold)
    except Exception:
        pass

    try:
        bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=1)
    except Exception:
        pass

    return {
        "status": "READY",
        "frame": int(frame),
        "threshold": float(threshold),
        "margin_px": int(margin_base),
        "min_distance_px": int(min_distance_base),
        "pre_ptrs": pre_ptrs,           # Achtung: Sets NICHT in Scene-Props loggen
        "new_count_raw": int(len(new)),
        "width": int(width),
        "height": int(height),
    }

# ---------------------------------------------------------------------
# Backward-Compat: run_detect_once (Thin-Wrapper)
# ---------------------------------------------------------------------
def run_detect_once(
    context: bpy.types.Context,
    *,
    start_frame: Optional[int] = None,
    threshold: Optional[float] = None,
    margin_base: Optional[int] = None,
    min_distance_base: Optional[int] = None,
    selection_policy: str = "only_new",
) -> Dict[str, Any]:
    """Kompatibler Wrapper ohne jegliche Nachbearbeitung/Triplets."""
    scn = bpy.context.scene
    if scn.get(_LOCK_KEY):
        return {"status": "FAILED", "reason": "locked"}
    scn[_LOCK_KEY] = True
    try:
        res = run_detect_basic(
            context,
            start_frame=start_frame,
            threshold=threshold,
            margin_base=margin_base,
            min_distance_base=min_distance_base,
            selection_policy=selection_policy,
        )
        if res.get("status") != "READY":
            return res
        return {
            "status": "READY",
            "frame": int(res.get("frame", bpy.context.scene.frame_current)),
            "threshold": float(res.get("threshold", 0.75)),
            "new_tracks": int(res.get("new_count_raw", 0)),
        }
    finally:
        try:
            scn[_LOCK_KEY] = False
        except Exception:
            pass
