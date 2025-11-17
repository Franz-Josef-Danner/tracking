from __future__ import annotations

import bpy
from typing import List, Tuple
import math

from .marker_positions_helper import get_positions

# ==========================================================
# Globale akkumulierte Werte
# ==========================================================
dx_var_accum = 0.0
dy_var_accum = 0.0
rel_var_accum = 0.0
global_p_dev_accum = 0.0
count = 0
countP = 0


def _evaluate_motion_model_pairwise(all_positions: list[tuple[float, float]],
                                    thresh_rot: float = 0.002,
                                    thresh_scale: float = 0.005,
                                    thresh_rot_scale_rot: float = 0.002,
                                    thresh_rot_scale_scale: float = 0.005) -> str:
    global dx_var_accum, dy_var_accum, rel_var_accum, count

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


    count += 1
    dx_var_accum += dx_var
    dy_var_accum += dy_var
    rel_var_accum += rel_var

    dx_var_mean = dx_var_accum / count
    dy_var_mean = dy_var_accum / count
    rel_var_mean = rel_var_accum / count
    print(f"[MotionModel][AVG] count={count} dx={dx_var_mean:.6f} dy={dy_var_mean:.6f} rel={rel_var_mean:.6f}")

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

def get_from_selected_tracks(context: bpy.types.Context, max_frames: int = 10) -> None:
    global dx_var_accum, dy_var_accum, rel_var_accum, global_p_dev_accum, countP, count
    """Analysiert Markerbewegung und setzt Motion Model (Loc / LocRot / LocScale / LocRotScale / Perspective)."""
    clip = getattr(context.space_data, "clip", None)
    if clip is None:
        return

    selected_tracks = [t for t in clip.tracking.tracks if t.select]
    if not selected_tracks:
        active_track = clip.tracking.tracks.active
        if active_track:
            selected_tracks = [active_track]
    if not selected_tracks:
        return
    scene = context.scene
    current_frame = scene.frame_current

    # --- Markerpositionen sammeln ---
    marker_positions: dict[str, list[tuple[float, float]]] = {}
    for track in selected_tracks:
        positions = get_positions(track, current_frame, max_frames=max_frames)
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
        
        countP += 1
        global_p_dev_accum += global_p_dev
        global_p_dev_accum_mean = global_p_dev_accum / countP
        print(f"[Perspective][AVG] countP={countP} global_p_dev={global_p_dev_accum_mean:.6f}")

        dx_var_mean = dx_var_accum / count if count else 0.0
        dy_var_mean = dy_var_accum / count if count else 0.0
        rel_var_mean = rel_var_accum / count if count else 0.0

        scene["kaiserlich_rot_thresh_x"] = dx_var_mean
        scene["kaiserlich_rot_thresh_y"] = dy_var_mean
        scene["kaiserlich_scale_thresh_max"] = rel_var_mean
        scene["kaiserlich_scale_thresh_min"] = rel_var_mean * 0.5
        scene["kaiserlich_rot_scale_thresh_rot"] = rel_var_mean
        scene["kaiserlich_rot_scale_thresh_scale"] = (dx_var_mean + dy_var_mean) * 0.5
        scene["kaiserlich_perspective_thresh"] = global_p_dev_accum_mean


    except Exception:
        pass
