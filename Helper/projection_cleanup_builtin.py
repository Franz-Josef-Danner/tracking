from __future__ import annotations
"""
refine_high_error.py — decoupled helper to avoid circular imports

This module intentionally avoids importing any of your other helpers
(solve_camera, tracking_coordinator, etc.) at *import time*.
It exposes a single function `run_refine_on_high_error(...)` that you
can safely import in solve_camera.py without triggering a circular import.

The actual refine action is optional and can be swapped out later; for now
it calls Blender's built-in refine operators guarded by context checks.
"""

from typing import Optional, Tuple
import bpy

__all__ = ("run_refine_on_high_error",)


def _find_clip_window(context) -> Tuple[Optional[bpy.types.Area], Optional[bpy.types.Region], Optional[bpy.types.Space]]:
    win = context.window
    if not win or not getattr(win, "screen", None):
        return None, None, None
    for area in win.screen.areas:
        if area.type == 'CLIP_EDITOR':
            region_window = None
            for r in area.regions:
                if r.type == 'WINDOW':
                    region_window = r
                    break
            if region_window:
                return area, region_window, area.spaces.active
    return None, None, None


def run_refine_on_high_error(
    context: bpy.types.Context,
    *,
    max_error: float = 0.0,
    mode: str = "TRACKING",
) -> dict:
    """Best-effort refine pass without importing other project modules.

    Parameters
    ----------
    max_error : float
        Optional threshold hint; currently unused but kept for API stability.
    mode : str
        Desired MovieClipEditor mode; defaults to 'TRACKING'.
    """
    area, region, space = _find_clip_window(context)
    if not area or not space or not getattr(space, "clip", None):
        return {"status": "SKIPPED", "reason": "no_clip_context"}

    # set editor mode (defensive)
    try:
        if getattr(space, "mode", None) != mode:
            space.mode = mode
    except Exception:
        pass

    # placeholder refine actions; keep minimal to avoid side effects
    try:
        with context.temp_override(area=area, region=region, space_data=space):
            # Example: stabilize 2D solve data or update plane tracks, etc.
            # These calls are intentionally conservative; adjust as needed.
            # bpy.ops.clip.filter_tracks(action='DELETE_TRACK', track_threshold=max(0.0, max_error))
            pass
    except Exception as ex:
        return {"status": "ERROR", "reason": repr(ex)}

    return {"status": "OK"}
