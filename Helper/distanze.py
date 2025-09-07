# SPDX-License-Identifier: GPL-2.0-or-later
"""
Helper/distanze.py
Löscht neu gesetzte, selektierte Marker, die näher als ein Mindestabstand
zu alten (nicht gemuteten) Markern liegen – alles am selben Frame.
Verbleibende neue Marker werden wieder selektiert.
"""
from __future__ import annotations
from typing import Iterable, Set, Dict, Any, Optional, Tuple
import math
import bpy
from mathutils import Vector

__all__ = ("run_distance_cleanup",)
DETECT_LAST_THRESHOLD_KEY = "last_detection_threshold"  # Fallback-Key, ohne Modulimport
LOG_PREFIX = "DISTANZE"

def _resolve_clip(context: bpy.types.Context) -> Optional[bpy.types.MovieClip]:
    scn = getattr(context, "scene", None)
    clip = getattr(context, "edit_movieclip", None)
    if clip:
        return clip
    space = getattr(context, "space_data", None)
    if space and getattr(space, "type", None) == "CLIP_EDITOR":
        clip = getattr(space, "clip", None)
        if clip:
            return clip
    clip = getattr(scn, "clip", None) if scn else None
    if clip:
        return clip
    try:
        for c in bpy.data.movieclips:
            return c
    except Exception:
        pass
    return None

def _ensure_clip_context() -> dict:
    """Find a CLIP_EDITOR override to ensure deletes are not no-ops."""
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
                return {"window": win, "area": area, "region": region, "space_data": space, "scene": bpy.context.scene}
    return {}

def _dist2(a: Vector, b: Vector, *, unit: str, clip_size: Optional[Tuple[float, float]]) -> float:
    if unit == "pixel" and clip_size:
        w, h = clip_size
        dx = (a.x - b.x) * w
        dy = (a.y - b.y) * h
        return dx * dx + dy * dy
    dx = a.x - b.x
    dy = a.y - b.y
    return dx * dx + dy * dy

def _compute_detect_min_distance(context: bpy.types.Context) -> tuple[int, float, float, int]:
    scn = context.scene
    base_px = int(scn.get("min_distance_base", 8))
    thr = float(scn.get(DETECT_LAST_THRESHOLD_KEY, 0.75))
    safe = max(thr * 1e8, 1e-8)
    factor = math.log10(safe) / 8.0
    detect_min_dist = max(1, int(base_px * factor))
    return detect_min_dist, thr, factor, base_px

def cleanup_new_markers_at_frame(
    context: bpy.types.Context,
    *,
    pre_ptrs: Iterable[int] | Set[int],
    frame: int,
    min_distance: float = 0.01,
    distance_unit: str = "pixel",
    require_selected_new: bool = True,
    include_muted_old: bool = False,
    select_remaining_new: bool = True,
) -> Dict[str, Any]:
    clip = _resolve_clip(context)
    if not clip:
        return {"status": "FAILED", "reason": "no_clip"}

    clip_size: Optional[Tuple[float, float]] = None
    if distance_unit == "pixel":
        try:
            clip_size = (float(clip.size[0]), float(clip.size[1]))
        except Exception:
            distance_unit = "normalized"

    auto_min_used = False
    auto_info: Dict[str, Any] = {}
    if min_distance is None or float(min_distance) <= 0.0:
        detect_min_px, thr, factor, base_px = _compute_detect_min_distance(context)
        min_distance = float(detect_min_px)
        distance_unit = "pixel"
        auto_min_used = True
        auto_info = {"auto_min_dist_px": int(detect_min_px), "thr": float(thr), "factor": float(factor), "base_px": int(base_px)}

    pre_ptrs_set: Set[int] = set(int(p) for p in (pre_ptrs or []))

    # Collect reference positions from OLD tracks (ignore muted/estimated)
    old_positions: list[Vector] = []
    for tr in clip.tracking.tracks:
        if int(tr.as_pointer()) in pre_ptrs_set:
            try:
                m = tr.markers.find_frame(int(frame), exact=True)
            except TypeError:
                m = tr.markers.find_frame(int(frame))
            if not m:
                continue
            if not include_muted_old and getattr(m, "mute", False):
                continue
            if getattr(m, "is_estimated", False):
                continue
            co = getattr(m, "co", None)
            if co is None:
                continue
            old_positions.append(co.copy())

    # New tracks = all tracks not in pre_ptrs
    new_tracks = [tr for tr in clip.tracking.tracks if int(tr.as_pointer()) not in pre_ptrs_set]

    min_d2 = float(min_distance) * float(min_distance)
    removed = 0
    kept = 0
    checked = 0
    skipped_no_marker = 0
    skipped_unselected = 0

    override = _ensure_clip_context()
    with bpy.context.temp_override(**override) if override else bpy.context.temp_override():
        for tr in new_tracks:
            try:
                m = tr.markers.find_frame(int(frame), exact=True)
            except TypeError:
                m = tr.markers.find_frame(int(frame))
            if not m:
                skipped_no_marker += 1
                continue
            if getattr(m, "is_estimated", False):
                # estimated Marker nicht als Konfliktbasis heranziehen
                skipped_no_marker += 1
                continue
            if require_selected_new and not (getattr(m, "select", False) or getattr(tr, "select", False)):
                skipped_unselected += 1
                continue

            pos = getattr(m, "co", None)
            if pos is None:
                skipped_no_marker += 1
                continue
            checked += 1

            nearest_d2 = float("inf")
            for old_pos in old_positions:
                d2 = _dist2(pos, old_pos, unit=distance_unit, clip_size=clip_size)
                if d2 < nearest_d2:
                    nearest_d2 = d2
            too_close = nearest_d2 < min_d2 if old_positions else False

            if too_close:
                # Log NUR für zu nahe Marker
                try:
                    print(f"[{LOG_PREFIX}] TooClose track={getattr(tr, 'name', '')} frame={frame} d2={nearest_d2:.4f}")
                except Exception:
                    pass
                # robustes Löschen: zuerst framegenau, dann Marker-Objekt
                try:
                    tr.markers.delete_frame(int(frame))
                    removed += 1
                    try:
                        print(f"[{LOG_PREFIX}] Deleted track={getattr(tr, 'name', '')} frame={frame} method=delete_frame")
                    except Exception:
                        pass
                    continue
                except Exception:
                    try:
                        tr.markers.delete(m)
                        removed += 1
                        try:
                            print(f"[{LOG_PREFIX}] Deleted track={getattr(tr, 'name', '')} frame={frame} method=delete(marker)")
                        except Exception:
                            pass
                        continue
                    except Exception:
                        # Keine weiteren Logs (nur TooClose/Deleted gewünscht)
                        continue

            if select_remaining_new:
                try:
                    m.select = True
                    tr.select = True
                except Exception:
                    pass
            kept += 1
    return {
        "status": "OK",
        "frame": int(frame),
        "removed": int(removed),
        "kept": int(kept),
        "checked_new": int(checked),
        "skipped_no_marker": int(skipped_no_marker),
        "skipped_unselected": int(skipped_unselected),
        "min_distance": float(min_distance),
        "distance_unit": distance_unit,
        "old_count": len(old_positions),
        "new_total": len(new_tracks),
        "auto_min_used": bool(auto_min_used),
        **auto_info,
    }

def run_distance_cleanup(
    context: bpy.types.Context,
    *,
    pre_ptrs: Iterable[int] | Set[int],
    frame: int,
    min_distance: Optional[float] = None,
    distance_unit: str = "pixel",
    require_selected_new: bool = True,
    include_muted_old: bool = False,
    select_remaining_new: bool = True,
) -> Dict[str, Any]:
    result = cleanup_new_markers_at_frame(
        context,
        pre_ptrs=pre_ptrs,
        frame=frame,
        min_distance=min_distance if (min_distance is not None) else -1.0,
        distance_unit=distance_unit,
        require_selected_new=require_selected_new,
        include_muted_old=include_muted_old,
        select_remaining_new=select_remaining_new,
    )
    return result
