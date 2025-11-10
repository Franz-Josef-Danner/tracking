# Helper/marker_position_forward_calibration.py
# ---------------------------------------------------------------------
# Marker-Korrektur über bis zu 4 Frames mit dynamischem Rückfall-System,
# robuster Mittelung (Trimming) und radialer Gewichtung.
# Automatische Wahl zwischen scene["good_marker"] und scene["best_marker"].
# Stellt sicher, dass selektierte Marker in allen relevanten Frames existieren.
# ---------------------------------------------------------------------

from typing import Iterable, List, Optional, Tuple
import bpy

# ----------------------------
# Low-level Marker Utilities
# ----------------------------

def _find_marker_at_frame(track: bpy.types.MovieTrackingTrack, frame: int) -> Optional[bpy.types.MovieTrackingMarker]:
    try:
        mk = track.markers.find_frame(frame)
        return mk if mk and not mk.mute else None
    except Exception:
        return None

def marker_exists(track: bpy.types.MovieTrackingTrack, frame: int) -> bool:
    return _find_marker_at_frame(track, frame) is not None

def get_marker_position(track: bpy.types.MovieTrackingTrack, frame: int) -> Tuple[float, float]:
    mk = _find_marker_at_frame(track, frame)
    if mk:
        return float(mk.co[0]), float(mk.co[1])
    head = track.markers[0] if track.markers else None
    return (float(head.co[0]), float(head.co[1])) if head else (0.0, 0.0)

def set_marker_position(track: bpy.types.MovieTrackingTrack, frame: int, x: float, y: float) -> None:
    mk = _find_marker_at_frame(track, frame)
    if mk:
        mk.co[0] = float(x)
        mk.co[1] = float(y)

def _active_clip(context: bpy.types.Context) -> Optional[bpy.types.MovieClip]:
    space = getattr(context, "space_data", None)
    return getattr(space, "clip", None) if space else None

def _iter_active_tracks_at_frame(context: bpy.types.Context, frame: int) -> Iterable[bpy.types.MovieTrackingTrack]:
    clip = _active_clip(context)
    if not clip:
        return []
    for tr in clip.tracking.tracks:
        if tr.select and marker_exists(tr, frame):
            yield tr

def get_active_markers(context: bpy.types.Context, frame: Optional[int]) -> List[bpy.types.MovieTrackingTrack]:
    if frame is None:
        return []
    return list(_iter_active_tracks_at_frame(context, int(frame)))

# ----------------------------
# Core Correction
# ----------------------------

def _select_good_set(scene: bpy.types.Scene) -> Optional[List[bpy.types.MovieTrackingTrack]]:
    has_good = "good_marker" in scene
    has_best = "best_marker" in scene
    if has_good and has_best:
        print("[MarkerCalib] ❌ Konflikt: Sowohl 'good_marker' als auch 'best_marker' vorhanden.")
        return None
    if has_good:
        print("[MarkerCalib] ✅ Verwende 'good_marker'-Set")
        return list(scene["good_marker"])
    if has_best:
        print("[MarkerCalib] ✅ Verwende 'best_marker'-Set")
        return list(scene["best_marker"])
    print("[MarkerCalib] ⚠️ Kein gültiges Referenzset vorhanden")
    return None

def _robust_weighted_mean(values_with_weights: List[Tuple[float, float]]) -> float:
    if not values_with_weights:
        return 0.0
    if len(values_with_weights) < 5:
        tw = sum(w for _, w in values_with_weights)
        return (sum(v * w for v, w in values_with_weights) / tw) if tw else 0.0
    sorted_vals = sorted(values_with_weights, key=lambda x: x[0])
    n = len(sorted_vals)
    cut = max(1, int(0.1 * n))
    trimmed = sorted_vals[cut:-cut] if n > 2 * cut else sorted_vals
    tw = sum(w for _, w in trimmed)
    return (sum(v * w for v, w in trimmed) / tw) if tw else 0.0

def correct_marker_positions(
    context: bpy.types.Context,
    selected_tracks: List[bpy.types.MovieTrackingTrack],
    frame_a: int,
    frame_b: int,
    frame_c: Optional[int] = None,
    frame_d: Optional[int] = None,
) -> None:
    print(f"\n[MarkerCalib] ---- Starte Marker-Korrektur ----")
    print(f"[MarkerCalib] Frames: A={frame_a}, B={frame_b}, C={frame_c}, D={frame_d}")
    print(f"[MarkerCalib] Selektierte Marker: {len(selected_tracks)}")

    scene = context.scene
    good_set = _select_good_set(scene)
    if good_set is None or len(good_set) == 0:
        print("[MarkerCalib] ❌ Abbruch – kein valider Referenzsatz.")
        return

    min_required = float(getattr(scene, "kaiserlich_markers_per_frame", 20)) / 2.0
    print(f"[MarkerCalib] Mindestanzahl Referenzmarker: {min_required}")

    fa_marker = get_active_markers(context, frame_a)
    fb_marker = get_active_markers(context, frame_b)
    fc_marker = get_active_markers(context, frame_c) if frame_c is not None else []
    fd_marker = get_active_markers(context, frame_d) if frame_d is not None else []

    fa_good = [m for m in fa_marker if m in good_set]
    fb_good = [m for m in fb_marker if m in good_set]
    fc_good = [m for m in fc_marker if m in good_set]
    fd_good = [m for m in fd_marker if m in good_set]

    print(f"[MarkerCalib] Gute Marker je Frame: A={len(fa_good)} B={len(fb_good)} C={len(fc_good)} D={len(fd_good)}")

    mode = 0
    source = []
    if frame_d is not None and len(fd_good) >= min_required:
        source = fd_good; mode = 4
    elif frame_c is not None and len(fc_good) >= min_required:
        source = fc_good; mode = 3
    elif len(fb_good) >= min_required:
        source = fb_good; mode = 2
    else:
        print("[MarkerCalib] ⚠️ Zu wenige stabile Referenzen – keine Korrektur.")
        return

    print(f"[MarkerCalib] ✅ Verwende Frame-Set Mode={mode} mit {len(source)} stabilen Referenzmarkern")

    relevant_frames = [frame for frame in (frame_a, frame_b, frame_c, frame_d) if frame is not None]

    for sm in selected_tracks:
        if not all(marker_exists(sm, f) for f in relevant_frames):
            print(f"[MarkerCalib] ⚠️ Überspringe {sm.name} – Marker fehlt in einem Frame.")
            continue

        fa_sm_x, fa_sm_y = get_marker_position(sm, frame_a)
        fb_sm_x, fb_sm_y = get_marker_position(sm, frame_b)

        weighted_vx: List[Tuple[float, float]] = []
        weighted_vy: List[Tuple[float, float]] = []

        for gm in source:
            if not all(marker_exists(gm, f) for f in relevant_frames):
                continue

            fa_gm_x, fa_gm_y = get_marker_position(gm, frame_a)
            fb_gm_x, fb_gm_y = get_marker_position(gm, frame_b)

            if mode >= 3 and frame_c is not None:
                fc_gm_x, fc_gm_y = get_marker_position(gm, frame_c)
            if mode == 4 and frame_d is not None:
                fd_gm_x, fd_gm_y = get_marker_position(gm, frame_d)

            if mode == 4:
                v_gm_x = 0.5 * ((fb_gm_x - fc_gm_x) + (fa_gm_x - fb_gm_x))
                v_gm_y = 0.5 * ((fb_gm_y - fc_gm_y) + (fa_gm_y - fb_gm_y))
            elif mode == 3:
                v_gm_x = 0.5 * ((fb_gm_x - fc_gm_x) + (fa_gm_x - fb_gm_x))
                v_gm_y = 0.5 * ((fb_gm_y - fc_gm_y) + (fa_gm_y - fb_gm_y))
            elif mode == 2:
                v_gm_x = (fa_gm_x - fb_gm_x)
                v_gm_y = (fa_gm_y - fb_gm_y)
            else:
                v_gm_x = 0.0
                v_gm_y = 0.0

            dx = fa_sm_x - fa_gm_x
            dy = fa_sm_y - fa_gm_y
            dist = (dx * dx + dy * dy) ** 0.5
            w = 1.0 / (1e-6 + dist)

            weighted_vx.append((v_gm_x, w))
            weighted_vy.append((v_gm_y, w))

        if not weighted_vx or not weighted_vy:
            print(f"[MarkerCalib] ⚠️ Keine gewichteten Werte für {sm.name} – übersprungen.")
            continue

        avg_vx = _robust_weighted_mean(weighted_vx)
        avg_vy = _robust_weighted_mean(weighted_vy)

        new_x = fb_sm_x + avg_vx
        new_y = fb_sm_y + avg_vy
        calib_x = 0.5 * (fa_sm_x + new_x)
        calib_y = 0.5 * (fa_sm_y + new_y)
        final_x = max(new_x * 0.95, min(new_x * 1.05, calib_x))
        final_y = max(new_y * 0.95, min(new_y * 1.05, calib_y))

        set_marker_position(sm, frame_a, final_x, final_y)
        print(f"[MarkerCalib] ✅ {sm.name} korrigiert: Δx={avg_vx:.5f}, Δy={avg_vy:.5f}, Final=({final_x:.5f}, {final_y:.5f})")

    print("[MarkerCalib] ---- Korrektur abgeschlossen ----\n")
