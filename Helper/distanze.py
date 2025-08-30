
from __future__ import annotations
from typing import Dict, Iterable, Optional, Set, Tuple, List
import bpy
from mathutils.kdtree import KDTree

__all__ = ["run_distance_cleanup"]

# Reuse-safe helpers (keine UI-Abhängigkeiten)
def _collect_positions_at_frame(
    tracks: Iterable[bpy.types.MovieTrackingTrack], frame: int, w: int, h: int
) -> List[Tuple[float, float]]:
    out = []
    for t in tracks:
        try:
            m = t.markers.find_frame(frame, exact=True)
        except TypeError:
            m = t.markers.find_frame(frame)
        if m and not getattr(m, "mute", False):
            out.append((m.co[0]*w, m.co[1]*h))
    return out

def _deselect_all(tracking: bpy.types.MovieTracking) -> None:
    for t in tracking.tracks:
        t.select = False

def _delete_selected_tracks(confirm: bool = True) -> None:
    try:
        bpy.ops.clip.delete_track(confirm=confirm)
    except Exception:
        pass

def run_distance_cleanup(
    context: bpy.types.Context,
    *,
    pre_ptrs: Set[int],
    frame: int,
    close_dist_rel: float = 0.01,
    reselect_only_remaining: bool = True,
) -> Dict:
    """
    Entfernt NEUE Marker, die näher als close_dist_rel * width an *vorhandene* Marker (pre_ptrs) herangerückt sind.
    Selektiert am Ende die verbleibenden NEUEN Marker.
    """
    scn = context.scene
    clip = getattr(context, "edit_movieclip", None) or getattr(getattr(context, "space_data", None), "clip", None)
    if not clip:
        for c in bpy.data.movieclips:
            clip = c
            break
    if not clip:
        return {"status": "FAILED", "reason": "no_movieclip"}

    tracking = clip.tracking
    width, height = int(clip.size[0]), int(clip.size[1])
    base_tracks = [t for t in tracking.tracks if t.as_pointer() in pre_ptrs]
    base_px = _collect_positions_at_frame(base_tracks, int(frame), width, height)
    kd: Optional[KDTree] = None
    if base_px:
        kd = KDTree(len(base_px))
        for i, (x, y) in enumerate(base_px):
            kd.insert((x, y, 0.0), i)
        kd.balance()

    # neue Marker = solche, die NICHT in pre_ptrs sind
    new_tracks = [t for t in tracking.tracks if t.as_pointer() not in pre_ptrs]
    if not kd or not new_tracks:
        # nur Selektion reparieren
        if reselect_only_remaining:
            _deselect_all(tracking)
            for t in new_tracks:
                t.select = True
        return {"status": "OK", "removed": 0, "remaining": len(new_tracks)}

    thr_px = max(1, int(width * (close_dist_rel if close_dist_rel > 0 else 0.01)))
    thr2 = float(thr_px * thr_px)

    reject_ptrs: Set[int] = set()
    for tr in new_tracks:
        try:
            m = tr.markers.find_frame(int(frame), exact=True)
        except TypeError:
            m = tr.markers.find_frame(int(frame))
        if not m or getattr(m, "mute", False):
            continue
        x = m.co[0] * width
        y = m.co[1] * height
        # robuster KD-Find (seltene Edge-Cases abfangen)
        try:
            (loc, _idx, _dist) = kd.find((x, y, 0.0))
        except Exception:
            # keine valide Nachbarschaft → so behandeln, als wäre es weit weg
            continue
        dx = x - loc[0]; dy = y - loc[1]
        if (dx*dx + dy*dy) < thr2:
            reject_ptrs.add(tr.as_pointer())
    if reject_ptrs:
        _deselect_all(tracking)
        for t in new_tracks:
            if t.as_pointer() in reject_ptrs:
                t.select = True
        try:
            _delete_selected_tracks(confirm=True)
        except Exception:
            # Fallback: harte Entfernung
            for t in list(tracking.tracks):
                if t.as_pointer() in reject_ptrs:
                    try:
                        tracking.tracks.remove(t)
                    except Exception:
                        pass

    # Reselektion: verbleibende neue
    remaining = [t for t in tracking.tracks if t.as_pointer() not in pre_ptrs]
    if reselect_only_remaining:
        _deselect_all(tracking)
        for t in remaining:
            t.select = True

    try:
        bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=1)
    except Exception:
        pass

    return {"status": "OK", "removed": int(len(reject_ptrs)), "remaining": int(len(remaining))}
