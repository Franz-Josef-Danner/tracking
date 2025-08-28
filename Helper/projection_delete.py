from __future__ import annotations

from typing import Optional, Tuple, Dict, Any, Iterable
import math
import bpy
import time
from ..Operator import tracking_coordinator as tco

__all__ = (
    "run_projection_cleanup_builtin",
)

# -----------------------------------------------------------------------------
# Kontext- und Error-Utilities (unverändert / leicht ergänzt)
# -----------------------------------------------------------------------------


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


def _active_clip(context) -> Optional[bpy.types.MovieClip]:
    space = getattr(context, "space_data", None)
    if getattr(space, "type", None) == 'CLIP_EDITOR' and getattr(space, "clip", None):
        return space.clip
    try:
        return bpy.data.movieclips[0] if bpy.data.movieclips else None
    except Exception:
        return None


def _get_current_solve_error_now(context) -> Optional[float]:
    clip = _active_clip(context)
    before_count = _count_tracks(clip)

    if delete_worst_only:
        worst = _find_worst_track(
            clip,
            include_muted=include_muted,
            require_min_markers=require_min_markers,
            require_has_bundle=require_has_bundle,
        )
        if worst is None:
            result = {
                "status": "SKIPPED",
                "reason": "no_valid_track_error",
                "used_error": None,
                "action": "DELETE_SINGLE_WORST",
                "before": before_count,
                "after": before_count,
                "deleted": 0,
                "selected": 0,
                "disabled": 0,
            }
            try:
                tco.on_projection_cleanup_finished(context=context)
            finally:
                return result

        obj, track, err = worst
        name = getattr(track, "name", "<unnamed>")
        ok = _delete_track(obj, track)
        _poke_update()
        after_count = _count_tracks(clip)
        deleted = 1 if ok and after_count == max(0, before_count - 1) else 0

        result = {
            "status": "OK" if ok else "ERROR",
            "used_error": err,
            "action": "DELETE_SINGLE_WORST",
            "reason": None if ok else "remove_failed",
            "before": before_count,
            "after": after_count,
            "deleted": deleted,
            "selected": 0,
            "disabled": 0,
            "track_name": name,
        }
        try:
            tco.on_projection_cleanup_finished(context=context)
        finally:
            return result

        obj, track, err = worst
        name = getattr(track, "name", "<unnamed>")
        ok = _delete_track(obj, track)
        after_count = _count_tracks(clip)
        deleted = 1 if ok and after_count == max(0, before_count - 1) else 0

        result = {
            "status": "OK" if ok else "ERROR",
            "used_error": err,
            "action": "DELETE_SINGLE_WORST",
            "reason": None if ok else "remove_failed",
            "before": before_count,
            "after": after_count,
            "deleted": deleted,
            "selected": 0,
            "disabled": 0,
            "track_name": name,
        }
        tco.on_projection_cleanup_finished(context=context)
        return result

    # ---- Altmodus (Schwellwert-basierter Cleanup) ----
    used_error: Optional[float] = None
    for val in (error_limit, threshold, max_error):
        if val is not None:
            used_error = float(val)
            break

    if used_error is None and wait_for_error:
        used_error = _wait_until_error(context, wait_forever=bool(wait_forever), timeout_s=float(timeout_s))

    if used_error is None:
        return {
            "status": "SKIPPED",
            "reason": "no_error",
            "used_error": None,
            "action": action,
            "before": before_count,
            "after": before_count,
            "deleted": 0,
            "selected": 0,
            "disabled": 0,
        }

    used_error = float(used_error) * 1.2

    try:
        _invoke_clean_tracks(context, used_error=float(used_error), action=str(action if action in _allowed_actions() else "SELECT"))
    except Exception as ex:
        return {
            "status": "ERROR",
            "reason": repr(ex),
            "used_error": used_error,
            "action": action,
            "before": before_count,
            "after": before_count,
            "deleted": 0,
            "selected": 0,
            "disabled": 0,
        }

    after_count = _count_tracks(clip)
    deleted = max(0, (before_count or 0) - (after_count or 0))


    tco.on_projection_cleanup_finished(context=context)

    return {
        "status": "OK",
        "used_error": used_error,
        "action": action,
        "reason": None,
        "before": before_count,
        "after": after_count,
        "deleted": deleted,
        "selected": 0,
        "disabled": 0,
    }
