# SPDX-License-Identifier: GPL-2.0-or-later
from __future__ import annotations

from typing import Any, Dict, Optional, Set, Tuple
import bpy
import math

__all__ = [
    "perform_marker_detection",
    "run_detect_basic",
    "run_detect_once",
]

# -----------------------------
# Scene Keys / State
# -----------------------------
DETECT_LAST_THRESHOLD_KEY = "last_detection_threshold"
_LOCK_KEY = "tco_detect_lock"  # mit Coordinator konsistent

# -----------------------------
# Helpers
# -----------------------------
def _get_movieclip(context: bpy.types.Context) -> Optional[bpy.types.MovieClip]:
    try:
        area = context.area
        if area and area.type == "CLIP_EDITOR":
            sp = area.spaces.active
            return getattr(sp, "clip", None)
    except Exception:
        pass
    # Fallback: aktive Szene
    try:
        return context.scene.clip
    except Exception:
        return None

def _ensure_clip_context(context: bpy.types.Context) -> Dict[str, Any]:
    """Findet einen CLIP_EDITOR und baut ein temp_override-Dict."""
    wm = bpy.context.window_manager
    if not wm:
        return {}
    for win in wm.windows:
        scr = getattr(win, "screen", None)
        if not scr:
            continue
        for area in scr.areas:
            if area.type != "CLIP_EDITOR":
                continue
            region = next((r for r in area.regions if r.type == "WINDOW"), None)
            space = area.spaces.active if hasattr(area, "spaces") else None
            if region and space:
                return {
                    "window": win,
                    "area": area,
                    "region": region,
                    "space_data": space,
                    "scene": bpy.context.scene,
                }
    return {}

def _detect_features(threshold: float) -> None:
    """Robuster Aufruf von bpy.ops.clip.detect_features im CLIP-Kontext."""
    def _op(**kw):
        try:
            return bpy.ops.clip.detect_features(**kw)
        except TypeError:
            return bpy.ops.clip.detect_features()

    override = _ensure_clip_context(bpy.context)
    if override:
        with bpy.context.temp_override(**override):
            _op(threshold=float(threshold))
    else:
        _op(threshold=float(threshold))

# -----------------------------
# Kern: Marker-Detection
# -----------------------------
def perform_marker_detection(
    clip: bpy.types.MovieClip,
    tracking: bpy.types.MovieTracking,
    threshold: float,
    margin_px: int,
    min_distance_px: int,
) -> Tuple[Set[int], int]:
    """Setzt Marker und gibt (pre_ptrs, new_count) zurück."""
    settings = tracking.settings
    try:
        settings.default_correlation_min = float(threshold)
    except Exception:
        pass
    try:
        settings.default_margin = int(margin_px)
    except Exception:
        pass
    try:
        settings.default_minimum_distance = int(min_distance_px)
    except Exception:
        pass

    # Vorher-Menge für Differenzbildung
    before = {t.as_pointer() for t in tracking.tracks}

    _detect_features(threshold=float(threshold))

    created = [t for t in tracking.tracks if t.as_pointer() not in before]
    return before, len(created)

# -----------------------------
# Public: Basic Detect
# -----------------------------
def run_detect_basic(
    context: bpy.types.Context,
    *,
    start_frame: Optional[int] = None,
    threshold: Optional[float] = None,
    margin_base: Optional[int] = None,
    min_distance_base: Optional[int] = None,
    selection_policy: Optional[str] = None,  # Placeholder für spätere Varianten
) -> Dict[str, Any]:
    """
    Setzt Marker am aktuellen (oder angegebenen) Frame und liefert Baseline-Infos.
    """
    scn = context.scene

    # Reentrancy-Schutz
    if scn.get(_LOCK_KEY):
        return {"status": "FAILED", "reason": "locked"}

    scn[_LOCK_KEY] = True  # <-- WICHTIG: eigene Zeile!

    try:
        clip = _get_movieclip(context)
        if not clip:
            return {"status": "FAILED", "reason": "no_movieclip"}

        if start_frame is not None:
            try:
                scn.frame_set(int(start_frame))
            except Exception:
                pass

        tracking = clip.tracking
        tracks = tracking.tracks

        # Defaults/Persistenz
        width = getattr(clip, "size", (0, 0))[0]
        height = getattr(clip, "size", (0, 0))[1]
        default_thr = float(scn.get(DETECT_LAST_THRESHOLD_KEY, 0.75))
        thr = float(threshold) if threshold is not None else default_thr
        margin = int(margin_base) if margin_base is not None else max(16, int(0.025 * max(width, height)))
        min_dist = int(min_distance_base) if min_distance_base is not None else max(8, int(0.05 * max(width, height)))

        pre_ptrs, new_count = perform_marker_detection(
            clip, tracking, thr, margin, min_dist
        )

        # Threshold persistieren
        scn[DETECT_LAST_THRESHOLD_KEY] = float(thr)

        return {
            "status": "READY",
            "frame": int(scn.frame_current),
            "threshold": float(thr),
            "margin_px": int(margin),
            "min_distance_px": int(min_dist),
            "pre_ptrs": pre_ptrs,
            "new_count_raw": int(new_count),
            "width": int(width),
            "height": int(height),
        }

    except Exception as ex:
        return {"status": "FAILED", "reason": f"{type(ex).__name__}: {ex}"}

    finally:
        try:
            scn[_LOCK_KEY] = False
        except Exception:
            pass

# -----------------------------
# Thin Wrapper für Backward-Compat
# -----------------------------
def run_detect_once(context: bpy.types.Context, **kwargs) -> Dict[str, Any]:
    res = run_detect_basic(context, **kwargs)
    if res.get("status") != "READY":
        return res
    return {
        "status": "READY",
        "frame": int(res.get("frame", bpy.context.scene.frame_current)),
        "threshold": float(res.get("threshold", 0.75)),
        "new_tracks": int(res.get("new_count_raw", 0)),
    }
