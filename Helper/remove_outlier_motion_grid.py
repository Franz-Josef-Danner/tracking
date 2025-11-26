# Helper/remove_outlier_motion_grid.py
# -------------------------------------------------------------------------
import bpy
import math
from typing import List, Tuple, Optional, Dict


# ------------------------------------------------------------
# INTERNAL: get valid marker location
# ------------------------------------------------------------
def _get_marker(track: bpy.types.MovieTrackingTrack, frame: int):
    try:
        m = track.markers.find_frame(frame)
        if m and not m.mute and m.enabled:
            return (m.co[0], m.co[1])
    except Exception:
        pass
    return None


# ------------------------------------------------------------
# INTERNAL: euclidean pixel distance
# ------------------------------------------------------------
def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


# ------------------------------------------------------------
# INTERNAL: collect tracks with continuous history at f, f-k
# ------------------------------------------------------------
def _collect_tracks(tracks, f, k):
    valid = []
    for t in tracks:
        if t.mute or t.lock:
            continue
        p0 = _get_marker(t, f)
        pk = _get_marker(t, f - k)
        if p0 and pk:
            valid.append((t, p0, pk))
    return valid


# ------------------------------------------------------------
# INTERNAL STAGE CHECK
#   Evaluates all (active) tracks vs. others, returns list of
#   tracks that exceed max_error and should be deleted.
# ------------------------------------------------------------
def _evaluate_tracks(track_data, max_error):
    """
    track_data: list[(track, p_now, p_past)]
    """
    flagged = set()
    ln = len(track_data)
    if ln < 2:
        return flagged

    for i in range(ln):
        ti, p0i, pki = track_data[i]
        vec_i = (p0i[0] - pki[0], p0i[1] - pki[1])

        # compute deviations relative to ALL others
        err_list = []
        for j in range(ln):
            if i == j:
                continue
            _, p0j, pkj = track_data[j]
            vec_j = (p0j[0] - pkj[0], p0j[1] - pkj[1])

            err = math.hypot(vec_i[0] - vec_j[0], vec_i[1] - vec_j[1])
            err_list.append(err)

        if not err_list:
            continue

        avg_err = sum(err_list) / len(err_list)
        if avg_err > max_error:
            flagged.add(ti)

    return flagged


# ------------------------------------------------------------
# INTERNAL GRID CLASSIFIER
# ------------------------------------------------------------
def _classify_into_grid(pos, nx, ny):
    """
    pos: (x, y) normalized [0..1]
    nx,ny: grid size
    returns grid index
    """
    x, y = pos
    ix = min(nx - 1, max(0, int(x * nx)))
    iy = min(ny - 1, max(0, int(y * ny)))
    return iy * nx + ix


# ------------------------------------------------------------
# MAIN PUBLIC FUNCTION
# ------------------------------------------------------------
def remove_outlier_motion_grid(context: bpy.types.Context):
    """
    Löscht Tracks mit unrealistischen Bewegungen in 3 Stufen:
     1) global
     2) 4er Raster
     3) 16er Raster

    Frames zurück: scene["kaiserlich_frames_per_track"] / 4
    Threshold in Pixel: scene["max_error_value"]
    """
    scene = context.scene
    clip = context.space_data.clip if context.space_data else None
    if clip is None:
        return {"CANCELLED"}

    tracks = [t for t in clip.tracking.tracks if (not t.mute and not t.lock)]

    # ----------------------------------------
    # PARAMETER
    # ----------------------------------------
    k_frames = int(max(1, scene.get("kaiserlich_frames_per_track", 4) // 4))
    max_error = float(scene.get("max_error_value", 3.0))
    f = scene.frame_current

    # ----------------------------------------
    # COLLECT VALID TRACKS
    # ----------------------------------------
    td = _collect_tracks(tracks, f, k_frames)
    if len(td) < 2:
        return {"CANCELLED"}

    to_delete = set()

    # ----------------------------------------
    # 1) GLOBAL PASS
    # ----------------------------------------
    to_delete |= _evaluate_tracks(td, max_error)

    # ----------------------------------------
    # 2) QUADRANT PASS (2x2)
    # ----------------------------------------
    if len(to_delete) < len(td):
        grid_map = {}
        for t, p0, pk in td:
            grid = _classify_into_grid(p0, 2, 2)
            grid_map.setdefault(grid, []).append((t, p0, pk))

        for _, lst in grid_map.items():
            to_delete |= _evaluate_tracks(lst, max_error)

    # ----------------------------------------
    # 3) 16 GRID PASS (4x4)
    # ----------------------------------------
    if len(to_delete) < len(td):
        grid_map = {}
        for t, p0, pk in td:
            grid = _classify_into_grid(p0, 4, 4)
            grid_map.setdefault(grid, []).append((t, p0, pk))

        for _, lst in grid_map.items():
            to_delete |= _evaluate_tracks(lst, max_error)

    # ----------------------------------------
    # FINAL DELETE
    # ----------------------------------------
    for t in to_delete:
        clip.tracking.tracks.remove(t)

    return {"FINISHED"}