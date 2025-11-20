# Helper.motion_average.py
from __future__ import annotations

import bpy
from typing import List, Tuple
import math
from .logging_helper import tracker_log

from .marker_positions_helper import get_positions

# ==========================================================
# Globale akkumulierte Werte
# ==========================================================
dx_var_accum = []
dy_var_accum = []
rel_var_accum = []
global_p_dev_accum = []
MAX_HISTORY = 10

# ----------------------------------------------------------
# Interner Helper: Frames-per-Track aus Szene lesen
# ----------------------------------------------------------
def _resolve_frames_per_track(scene: bpy.types.Scene, fallback: int = 5) -> int:
    value = None
    try:
        if hasattr(scene, "kaiserlich_frames_per_track"):
            value = getattr(scene, "kaiserlich_frames_per_track")
        elif "kaiserlich_frames_per_track" in scene:
            value = scene["kaiserlich_frames_per_track"]
    except Exception:
        value = None

    if value is None:
        value = fallback

    try:
        value = int(value)
    except Exception:
        value = fallback

    if value < 2:
        value = 2
    return value

def _evaluate_motion_model_pairwise(all_positions: list[tuple[float, float]],
                                    thresh_rot: float = 0.002,
                                    thresh_scale: float = 0.005,
                                    thresh_rot_scale_rot: float = 0.002,
                                    thresh_rot_scale_scale: float = 0.005) -> str:
    global dx_var_accum, dy_var_accum, rel_var_accum, MAX_HISTORY

    if len(all_positions) < 2:
        return "Loc"

    rel_distances = []
    avg_x_values = []
    avg_y_values = []

    for i in range(len(all_positions) - 1):
        (x1, y1), (x2, y2) = all_positions[i], all_positions[i + 1]
        avg_x_values.append((x1 + x2) / 2.0)
        avg_y_values.append((y1 + y2) / 2.0)
        rel_distances.append((abs(x1 - x2) + abs(y1 - y2)) / 2.0)

    if not rel_distances:
        return "Loc"

    dx_var = max(avg_x_values) - min(avg_x_values)
    dy_var = max(avg_y_values) - min(avg_y_values)
    rel_var = max(rel_distances) - min(rel_distances)

    dx_var_accum.append(dx_var)
    dy_var_accum.append(dy_var)
    rel_var_accum.append(rel_var)

    if len(dx_var_accum) > MAX_HISTORY: dx_var_accum.pop(0)
    if len(dy_var_accum) > MAX_HISTORY: dy_var_accum.pop(0)
    if len(rel_var_accum) > MAX_HISTORY: rel_var_accum.pop(0)

    dx_var_mean = sum(dx_var_accum) / len(dx_var_accum)
    dy_var_mean = sum(dy_var_accum) / len(dy_var_accum)
    rel_var_mean = sum(rel_var_accum) / len(rel_var_accum)

    # Klassifikation ohne Veränderung
    if (
        rel_var > thresh_rot_scale_scale
        and (dx_var > thresh_rot_scale_rot or dy_var > thresh_rot_scale_rot)
    ):
        return "LocRotScale"
    elif rel_var > thresh_scale:
        return "LocScale"
    elif dx_var > thresh_rot or dy_var > thresh_rot:
        return "LocRot"
    else:
        return "Loc"


# ==========================================================
# Perspective-Erkennung (Mittelpunktanalyse)
# ==========================================================

def _detect_perspective_motion(marker_positions: dict[str, list[tuple[float, float]]],
                               perspective_thresh: float = 0.002
                               ) -> tuple[str | None, float, dict[str, float]]:
    """
    Bestimmt Mittelpunkt-Marker und prüft perspektivische Abweichung.
    Rückgabe: (center_marker, max_dev, per_marker_dev_dict)
    - center_marker: Name des Markers mit geringster Gesamtbewegung
    - max_dev: größte Abweichung ggü. Mittelwert der mv_i über alle Marker
    - per_marker_dev_dict: Abweichung je Marker (für per-Marker-Perspective)
    """

    if not marker_positions:
        return None, 0.0, {}

    # 1) Bewegungslänge pro Marker (mpd_i)
    total_movement = {}
    for name, positions in marker_positions.items():
        if len(positions) < 2:
            continue
        mpf_values = [(x + y) / 2.0 for x, y in positions]
        mpd_i = sum(abs(mpf_values[i+1] - mpf_values[i]) for i in range(len(mpf_values) - 1))
        total_movement[name] = mpd_i

    if not total_movement:
        return None, 0.0, {}

    # 2) Mittelpunkt = Marker mit geringster Bewegung
    center_marker = min(total_movement, key=total_movement.get)
    center_positions = marker_positions[center_marker]
    mmx = sum(x for x, _ in center_positions) / len(center_positions)
    mmy = sum(y for _, y in center_positions) / len(center_positions)

    # 3) Abstände zum Mittelpunkt je Frame und deren Veränderung (mv_i)
    mv_values = {}
    for name, positions in marker_positions.items():
        if len(positions) < 2:
            continue
        md_list = [(abs(mmx - x) + abs(mmy - y)) / 2.0 for x, y in positions]
        mv_i = sum(md_list[i] - md_list[i + 1] for i in range(len(md_list) - 1))
        mv_values[name] = mv_i

    if not mv_values:
        return center_marker, 0.0, {}

    mvth = sum(abs(v) for v in mv_values.values()) / len(mv_values)

    # 4) Abweichungen je Marker
    per_marker_dev: dict[str, float] = {}
    for name, mv_i in mv_values.items():
        per_marker_dev[name] = abs(mv_i - mvth)

    max_dev = max(per_marker_dev.values()) if per_marker_dev else 0.0
    return center_marker, max_dev, per_marker_dev






# ==========================================================
# Hauptlogik – Hybrid-Auswertung + Perspective
# ==========================================================

def get_calibrate_tracks(
    context: bpy.types.Context,
    max_frames: int | None = None,
) -> None:
    global dx_var_accum, dy_var_accum, rel_var_accum, global_p_dev_accum, MAX_HISTORY
    """Analysiert Markerbewegung und setzt Motion Model (Loc / LocRot / LocScale / LocRotScale / Perspective)."""
    clip = getattr(context.space_data, "clip", None)
    if clip is None:
        tracker_log("MOTION", "FORWARD", "skip:no_clip")
        return

    scene = context.scene
    current_frame = scene.frame_current
    frames_per_track = _resolve_frames_per_track(scene, max_frames if (max_frames is not None and max_frames > 0) else 5)

    # ============================================================
    # NEU: Nur calibrate_tracks verwenden – nie Selection/Active
    # ============================================================
    calibrate_raw = scene.get("calibrate_tracks", [])
    if isinstance(calibrate_raw, str):
        calibrate_names = [t.strip() for t in calibrate_raw.split(",") if t.strip()]
    elif isinstance(calibrate_raw, (list, tuple)):
        calibrate_names = [t for t in calibrate_raw]
    else:
        calibrate_names = []

    tracker_log("MOTION", "FORWARD", f"start frame={current_frame} candidates={len(calibrate_names)} span={frames_per_track}")

    selected_tracks = []
    for name in calibrate_names:
        tr = clip.tracking.tracks.get(name)
        if not tr:
            continue
        pos = get_positions(tr, current_frame, frames_per_track)
        if len(pos) >= 2:
            selected_tracks.append(tr)

    if not selected_tracks:
        tracker_log("MOTION", "FORWARD", "skip:no_valid_tracks")
        return

    scene = context.scene
    current_frame = scene.frame_current

    # Frames-per-Track aus Szene beziehen (Fallback: max_frames oder 5)
    default_frames = max_frames if (max_frames is not None and max_frames > 0) else 5
    frames_per_track = _resolve_frames_per_track(scene, default_frames)

    # --- Markerpositionen sammeln ---
    marker_positions: dict[str, list[tuple[float, float]]] = {}
    for track in selected_tracks:
        positions = get_positions(
            track,
            current_frame,
            max_frames=frames_per_track,
        )
        if len(positions) >= 2:
            marker_positions[track.name] = [(x, y) for _, (x, y) in positions]
    if not marker_positions:
        tracker_log("MOTION", "FORWARD", "skip:no_marker_positions")
        return

    try:
        # --- 1) Globales Modell aus Mittelwerten ---
        all_positions = []
        for pts in marker_positions.values():
            mean_x = sum(x for x, _ in pts) / len(pts)
            mean_y = sum(y for _, y in pts) / len(pts)
            all_positions.append((mean_x, mean_y))

        rot_t = getattr(scene, "kaiserlich_rot_thresh_x", 0.002)
        scale_t = getattr(scene, "kaiserlich_scale_thresh_max", 0.005)
        rs_rot_t = getattr(scene, "kaiserlich_rot_scale_thresh_rot", 0.002)
        rs_scale_t = getattr(scene, "kaiserlich_rot_scale_thresh_scale", 0.005)
        persp_t = getattr(scene, "kaiserlich_perspective_thresh", 0.002)
        global_model = _evaluate_motion_model_pairwise(
            all_positions,
            rot_t,
            scale_t,
            rs_rot_t,
            rs_scale_t
        )

        # --- 2) Perspective global & per Marker einmalig berechnen ---
        _, global_p_dev, per_marker_dev = _detect_perspective_motion(
            marker_positions,
            persp_t
        )
        perspective_thresh = persp_t
        if global_p_dev > perspective_thresh:
            global_model = "Perspective"
        tracker_log("MOTION", "FORWARD", f"evaluate model={global_model} tracks={len(selected_tracks)} g_p_dev={global_p_dev:.6f}")
        
        global_p_dev_accum.append(global_p_dev)
        if len(global_p_dev_accum) > MAX_HISTORY: global_p_dev_accum.pop(0)
        global_p_dev_accum_mean = sum(global_p_dev_accum) / len(global_p_dev_accum)

        dx_var_mean = sum(dx_var_accum) / len(dx_var_accum) if dx_var_accum else 0.0
        dy_var_mean = sum(dy_var_accum) / len(dy_var_accum) if dy_var_accum else 0.0
        rel_var_mean = sum(rel_var_accum) / len(rel_var_accum) if rel_var_accum else 0.0

        scene["kaiserlich_rot_thresh_x"] = max(0, min(1, 1 - ((((1 - dx_var_mean) * 0.009781) * 500.7511267) - 0.25)))
        scene["kaiserlich_rot_thresh_y"] = max(0, min(1, 1 - ((((1 - dy_var_mean) * 0.017600) * 279.0957298) - 0.48)))
        scene["kaiserlich_scale_thresh_min"] = max(0, min(1, 1 - ((((1 - rel_var_mean) * 0.000330) * 9803.921569) - 0.66)))
        scene["kaiserlich_scale_thresh_max"] = max(0, min(1, 1 - ((((1 - rel_var_mean) * 0.000364) * 8876.523582) - 0.66)))
        scene["kaiserlich_rot_scale_thresh_rot"] = max(0, min(1, 1 - (((((((1 - dx_var_mean)) + ((1 - dy_var_mean))) / 2) * 0.015670) * 376.2227239) - 0.57)))
        scene["kaiserlich_rot_scale_thresh_scale"] = max(0, min(1,  1 - ((((1 - rel_var_mean) * 0.000347) * 11111.11111) - 0.79)))
        scene["kaiserlich_perspective_thresh"] = max(0, min(1, 1 - ((((1 - global_p_dev_accum_mean) * 0.008706) * 657.0302234) - 4.70)))
        tracker_log("MOTION", "FORWARD", f"update dx_var_mean={dx_var_mean:.6f} dy_var_mean={dy_var_mean:.6f} rel_var_mean={rel_var_mean:.6f} g_p_dev_mean={global_p_dev_accum_mean:.6f}")
        tracker_log("MOTION", "FORWARD", "done:update_thresholds")
        
    except Exception:
        tracker_log("MOTION", "FORWARD", "error:exception")
        pass
