# Helper.motion_average.py
from __future__ import annotations

import bpy
from typing import List, Tuple
import math

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

def get_from_selected_tracks(
    context: bpy.types.Context,
    max_frames: int | None = None,
) -> None:
    global dx_var_accum, dy_var_accum, rel_var_accum, global_p_dev_accum, MAX_HISTORY
    """Analysiert Markerbewegung und setzt Motion Model (Loc / LocRot / LocScale / LocRotScale / Perspective)."""
    clip = getattr(context.space_data, "clip", None)
    if clip is None:
        return

    scene = context.scene
    current_frame = scene.frame_current
    frames_per_track = _resolve_frames_per_track(scene, max_frames if (max_frames is not None and max_frames > 0) else 5)

    candidate_tracks = []
    for track in clip.tracking.tracks:
        positions = get_positions(track, current_frame, frames_per_track)
        if len(positions) >= 2:
            candidate_tracks.append(track)

    if candidate_tracks:
        selected_tracks = candidate_tracks
    else:
        # Fallback: bisherige Logik
        selected_tracks = [t for t in clip.tracking.tracks if t.select]
        if not selected_tracks and clip.tracking.tracks.active:
            selected_tracks = [clip.tracking.tracks.active]

    if not selected_tracks:
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
        return

    try:
        # --- 1) Globales Modell aus Mittelwerten ---
        all_positions = []
        for pts in marker_positions.values():
            mean_x = sum(x for x, _ in pts) / len(pts)
            mean_y = sum(y for _, y in pts) / len(pts)
            all_positions.append((mean_x, mean_y))

        global_model = _evaluate_motion_model_pairwise(
            all_positions,
            getattr(scene, "kaiserlich_rot_thresh_x", 0.002),
            getattr(scene, "kaiserlich_scale_thresh_max", 0.005),
            getattr(scene, "kaiserlich_rot_scale_thresh_rot", 0.002),
            getattr(scene, "kaiserlich_rot_scale_thresh_scale", 0.005)
        )

        # --- 2) Perspective global & per Marker einmalig berechnen ---
        _, global_p_dev, per_marker_dev = _detect_perspective_motion(
            marker_positions,
            getattr(scene, "kaiserlich_perspective_thresh", 0.002)
        )
        perspective_thresh = getattr(scene, "kaiserlich_perspective_thresh", 0.002)
        
        global_p_dev_accum.append(global_p_dev)
        if len(global_p_dev_accum) > MAX_HISTORY: global_p_dev_accum.pop(0)
        global_p_dev_accum_mean = sum(global_p_dev_accum) / len(global_p_dev_accum)

        dx_var_mean = sum(dx_var_accum) / len(dx_var_accum) if dx_var_accum else 0.0
        dy_var_mean = sum(dy_var_accum) / len(dy_var_accum) if dy_var_accum else 0.0
        rel_var_mean = sum(rel_var_accum) / len(rel_var_accum) if rel_var_accum else 0.0

        # ============================================================
        # Aktuelle Motion Models der selektierten Tracks auslesen
        # und Anzahl je Typ in Szene-Variablen speichern
        # ============================================================
        model_counts = {
            "Loc": 0,
            "LocRot": 0,
            "LocScale": 0,
            "LocRotScale": 0,
            "Perspective": 0,
        }

        for track in selected_tracks:
            mm = getattr(track, "motion_model", None)
            if mm in model_counts:
                model_counts[mm] += 1

        for key, val in model_counts.items():
            scene[f"kaiserlich_model_count_{key}"] = val

        rel_var_min = rel_var_mean * 0.5
        rel_var_multi_min = rel_var_multi * 0.5

        d_var_com = (dx_var_mean + dy_var_mean) / 2
        d_var_multi_com = (dx_var_multi + dy_var_multi) / 2

        rel_com = rel_var_mean * 0.25

        mo_full = loc + LocRot + LocScale + LocRotScale + Perspective
        mo_full_loc = (100 / mo_full) * loc
        mo_full_locrot = (100 / mo_full) * LocRot
        mo_full_locscale = (100 / mo_full) * LocScale
        mo_full_locrotscale = (100 / mo_full) * LocRotScale
        mo_full_perspective = (100 / mo_full) * Perspective

        th_full = dx_var_mean + dy_var_mean + rel_var_mean + rel_var_min + d_var_com + rel_com + global_p_dev_accum_mean
        th_full_dx = (100 / th_full) * dx_var_mean
        th_full_dy = (100 / th_full) * dy_var_mean
        th_full_rel = (100 / th_full) * rel_var_mean
        th_full_rel_min = (100 / th_full) * rel_var_min
        th_full_dcom = (100 / th_full) * d_var_com
        th_full_relcom = (100 / th_full) * rel_com
        th_full_perspective = (100 / th_full) * global_p_dev_accum_mean

        mo_full_loc_x = (100 / mo_full_loc) * th_full_dx
        mo_full_loc_y = (100 / mo_full_loc) * th_full_dy

        dx_var_mean_mult = dx_var_mean * (th_full_dx / mo_full_loc_x)
        dy_var_mean_mult = dy_var_mean * (th_full_dy / mo_full_loc_y)

        mo_full_rel_max = (100 / mo_full_locrot) * th_full_rel
        mo_full_rel_min = (100 / mo_full_locrot) * th_full_rel_min

        rel_var_mean_mult = rel_var_mean * (th_full_rel / mo_full_rel_max)
        rel_var_min_mult = rel_var_min * (th_full_rel_min / mo_full_rel_min)

        mo_full_locrotscale_rot = (100 / mo_full_locrotscale) * th_full_dcom
        mo_full_locrotscale_scale = (100 / mo_full_locrotscale) * th_full_relcom

        d_var_com_mult = d_var_com * (th_full_dcom / mo_full_locrotscale_rot)
        rel_com_mult = rel_com * (th_full_relcom / mo_full_locrotscale_scale)

        global_p_dev_accum_mean_mult = global_p_dev_accum_mean * (th_full_perspective / mo_full_perspective)

        # Szene-Multiplikatoren einlesen (numerisch, Fallback 0.0)
        dx_var_multi = float(scene.get('dx_var_multi', 0.0))
        dy_var_multi = float(scene.get('dy_var_multi', 0.0))
        rel_var_multi = float(scene.get('rel_var_multi', 0.0))
        global_p_multi = float(scene.get('global_p_multi', 0.0))

    
        if dx_var_multi < dx_var_mean:
            if dx_var_mean > 0:
                dx_var_multi = dx_var_mean
                dx_var_multiply = 1.0 / dx_var_mean
            else:
                pass
        else:
            pass

        if dy_var_multi < dy_var_mean:
            if dy_var_mean > 0:
                dy_var_multi = dy_var_mean
                dy_var_multiply = 1.0 / dy_var_mean
            else:
                pass
        else:
            pass

        if rel_var_multi < rel_var_mean:
            if rel_var_mean > 0:
                rel_var_multi = rel_var_mean
                rel_var_multiply = 1.0 / rel_var_mean
            else:
                pass
        else:
            pass

        if rel_var_multi_min < rel_var_min:
            if rel_var_min > 0:
                rel_var_multi_min = rel_var_min
                rel_var_min_multiply = 1.0 / rel_var_min
            else:
                pass
        else:
            pass

        if d_var_multi_com < d_var_com:
            if d_var_com > 0:
                d_var_multi_com = d_var_com
                d_var_multiply_com = 1.0 / d_var_com
            else:
                pass
        else:
            pass

        if rel_var_multi < rel_com:
            if rel_com > 0:
                rel_var_multi = rel_com
                rel_var_multiply = 1.0 / rel_com
            else:
                pass
        else:
            pass

        if global_p_multi < global_p_dev_accum_mean:
            if global_p_dev_accum_mean > 0:
                global_p_multi = global_p_dev_accum_mean
                global_p_multiply = 1.0 / global_p_dev_accum_mean
            else:
                pass
        else:
            pass

        dx_var_mean = dx_var_mean * dx_var_mean_mult
        dy_var_mean = dy_var_mean * dy_var_mean_mult
        rel_var_mean = rel_var_mean * rel_var_mean_mult
        rel_var_min = rel_var_min * rel_var_min_mult
        d_var_com = d_var_com * d_var_com_mult
        rel_com = rel_com * rel_com_mult
        global_p_dev_accum_mean = global_p_dev_accum_mean * global_p_dev_accum_mean_mult

        scene["dx_var_multiply"] = dx_var_multiply
        scene["rel_var_multiply"] = rel_var_multiply
        scene["d_var_multiply_com"] = d_var_multiply_com
        scene["rel_var_multiply"] = rel_var_multiply
        scene["global_p_multiply"] = global_p_multiply

        scene["kaiserlich_rot_thresh_x"] = dx_var_mean * dx_var_multiply
        scene["kaiserlich_rot_thresh_y"] = dy_var_mean * dy_var_multiply
        scene["kaiserlich_scale_thresh_min"] = rel_var_min * rel_var_min_multiply
        scene["kaiserlich_scale_thresh_max"] = rel_var_mean * rel_var_multiply
        scene["kaiserlich_rot_scale_thresh_rot"] = d_var_com * d_var_multiply_com
        scene["kaiserlich_rot_scale_thresh_scale"] = rel_com * rel_var_multiply
        scene["kaiserlich_perspective_thresh"] = global_p_dev_accum_mean * global_p_multiply
        
    except Exception:
        pass
