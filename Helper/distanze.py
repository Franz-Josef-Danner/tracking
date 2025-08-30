
from __future__ import annotations
from typing import Dict, Iterable, Optional, Set, Tuple, List
import bpy
from typing import Any
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

# --- Compatibility helpers for Blender ≥ 4.4 (Marker.select entfernt) -----
def _marker_get_select(m: Any, t: bpy.types.MovieTrackingTrack) -> bool:
    """Best effort: Marker-Selektionsflag lesen; Fallback auf Track.select."""
    try:
        return bool(getattr(m, "select"))
    except Exception:
        return bool(getattr(t, "select", False))

def _marker_set_select(m: Any, t: bpy.types.MovieTrackingTrack, value: bool) -> None:
    """Best effort: Marker-Selektionsflag setzen; Fallback auf Track.select."""
    try:
        setattr(m, "select", bool(value))
    except Exception:
        try:
            t.select = bool(value)
        except Exception:
            # Let it go – kein Crash, UI-Flag ist rein kosmetisch
            pass

def run_distance_cleanup(
    context: bpy.types.Context,
    *,
    pre_ptrs: Set[int],
    frame: int,
    close_dist_rel: float = 0.01,
    reselect_only_remaining: bool = True,
    select_remaining_new: bool = True,
    select_remaining_new: bool = True,
) -> Dict:
    """
    Entfernt NEUE Marker, die näher als close_dist_rel * width an *vorhandene* Marker (pre_ptrs) liegen.
    Selektiert am Ende – falls select_remaining_new=True – die verbleibenden NEUEN Tracks/Marker
    am gegebenen Frame (für koordinierte Folge-Operationen wie Delete).
    Andernfalls wird – bei reselect_only_remaining=True – nur der ursprüngliche Snapshot wiederhergestellt.
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

    # neue Marker/Tracks = solche, die NICHT in pre_ptrs sind
    new_tracks = [t for t in tracking.tracks if t.as_pointer() not in pre_ptrs]

    # --- NEU: Snapshot der Selektion nur für NEUE Tracks (minimal-invasiv) ---
    # Wir sichern sowohl die Track-Selektion als auch die Marker-Selektion am aktuellen Frame.
    sel_snapshot_tracks = {t.as_pointer(): bool(getattr(t, "select", False)) for t in new_tracks}
    sel_snapshot_marker_at_f = {}
    for t in new_tracks:
        try:
            m = t.markers.find_frame(int(frame), exact=True)
        except TypeError:
            m = t.markers.find_frame(int(frame))
        if m:
            sel_snapshot_marker_at_f[t.as_pointer()] = _marker_get_select(m, t)
    if not kd or not new_tracks:
        if select_remaining_new:
            for t in new_tracks:
                try:
                    t.select = True
                    try:
                        m = t.markers.find_frame(int(frame), exact=True)
                    except TypeError:
                        m = t.markers.find_frame(int(frame))
                    if m:
                        _marker_set_select(m, t, True)
                except Exception:
                    pass
        elif reselect_only_remaining:
            for t in new_tracks:
                t.select = sel_snapshot_tracks.get(t.as_pointer(), False)
                try:
                    m = t.markers.find_frame(int(frame), exact=True)
                except TypeError:
                    m = t.markers.find_frame(int(frame))
                if m is not None and t.as_pointer() in sel_snapshot_marker_at_f:
                    _marker_set_select(m, t, sel_snapshot_marker_at_f[t.as_pointer()])
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
        # Tracks gezielt für den Operator selektieren, danach Snapshot-Selektionszustand wiederherstellen
        # 1) Alle neuen Tracks temporär deselektieren
        for t in new_tracks:
            t.select = False
        # 2) Nur die abzulehnenden selektieren → delete_track löscht exakt diese
        for t in new_tracks:
            if t.as_pointer() in reject_ptrs:
                t.select = True
        # 3) Löschen
        hard_removed: Set[int] = set()
        try:
            _delete_selected_tracks(confirm=True)
            hard_removed = reject_ptrs.copy()
        except Exception:
            # Fallback: harte Entfernung per API
            for t in list(tracking.tracks):
                if t.as_pointer() in reject_ptrs:
                    try:
                        tracking.tracks.remove(t)
                        hard_removed.add(t.as_pointer())
                    except Exception:
                        pass
        # 4) Ursprungs-Selektion für verbleibende neue Tracks wiederherstellen
        if reselect_only_remaining:
            for t in tracking.tracks:
                tptr = t.as_pointer()
                if tptr in pre_ptrs:
                    # Alte (Basis-)Tracks fassen wir nicht an
                    continue
                if tptr in hard_removed:
                    # Existiert nicht mehr
                    continue
                # Track-Selektionsstatus zurücksetzen
                if tptr in sel_snapshot_tracks:
                    t.select = sel_snapshot_tracks[tptr]
                # Marker-Selektion am Frame zurücksetzen
                try:
                    m = t.markers.find_frame(int(frame), exact=True)
                except TypeError:
                    m = t.markers.find_frame(int(frame))
                if m is not None and tptr in sel_snapshot_marker_at_f:
                    _marker_set_select(m, t, sel_snapshot_marker_at_f[tptr])

    remaining = [t for t in tracking.tracks if t.as_pointer() not in pre_ptrs]
    if select_remaining_new:
        for t in remaining:
            try:
                t.select = True
                try:
                    m = t.markers.find_frame(int(frame), exact=True)
                except TypeError:
                    m = t.markers.find_frame(int(frame))
                if m:
                    _marker_set_select(m, t, True)
            except Exception:
                pass
    elif reselect_only_remaining:
        for t in remaining:
            tptr = t.as_pointer()
            t.select = sel_snapshot_tracks.get(tptr, getattr(t, "select", False))
            try:
                m = t.markers.find_frame(int(frame), exact=True)
            except TypeError:
                m = t.markers.find_frame(int(frame))
            if m is not None and tptr in sel_snapshot_marker_at_f:
                _marker_set_select(m, t, sel_snapshot_marker_at_f[tptr])
            except Exception:
                pass
    elif reselect_only_remaining:
        # Snapshot der neuen Tracks/Marker wiederherstellen (nicht-invasiv)
        for t in remaining:
            tptr = t.as_pointer()
            t.select = sel_snapshot_tracks.get(tptr, getattr(t, "select", False))
            try:
                m = t.markers.find_frame(int(frame), exact=True)
            except TypeError:
                m = t.markers.find_frame(int(frame))
            if m is not None and tptr in sel_snapshot_marker_at_f:
                _marker_set_select(m, t, sel_snapshot_marker_at_f[tptr])

    try:
        bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=1)
    except Exception:
        pass

    return {"status": "OK", "removed": int(len(reject_ptrs)), "remaining": int(len(remaining))}
