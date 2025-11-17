# Helper.motion_average_backwards.py
from __future__ import annotations

import bpy
from typing import List, Tuple
import math

from .marker_positions_helper import get_positions

# ==========================================================
# Globale akkumulierte Werte (separat für rückwärts!)
# ==========================================================
dx_var_accum_bw: list[float] = []
dy_var_accum_bw: list[float] = []
rel_var_accum_bw: list[float] = []
global_p_dev_accum_bw: list[float] = []
MAX_HISTORY = 10


# ==========================================================
# Bewegungsmodell-Evaluierung (Loc, LocRot, LocScale, LocRotScale) – rückwärts
# ==========================================================
def _evaluate_motion_model_pairwise_backwards(
    all_positions: list[tuple[float, float]],
    thresh_rot: float = 0.002,
    thresh_scale: float = 0.005,
    thresh_rot_scale_rot: float = 0.002,
    thresh_rot_scale_scale: float = 0.005,
) -> str:
    """
    Gleiche Logik wie _evaluate_motion_model_pairwise (vorwärts),
    aber mit eigenen BW-Akkumulatoren.
    """
    global dx_var_accum_bw, dy_var_accum_bw, rel_var_accum_bw

    if len(all_positions) < 2:
        return "Loc"

    # Reihenfolge NICHT nach x/y sortieren → wir vertrauen der Sequenz von get_positions()
    rel_distances: list[float] = []
    avg_x_values: list[float] = []
    avg_y_values: list[float] = []

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

    dx_var_accum_bw.append(dx_var)
    dy_var_accum_bw.append(dy_var)
    rel_var_accum_bw.append(rel_var)

    if len(dx_var_accum_bw) > MAX_HISTORY:
        dx_var_accum_bw.pop(0)
    if len(dy_var_accum_bw) > MAX_HISTORY:
        dy_var_accum_bw.pop(0)
    if len(rel_var_accum_bw) > MAX_HISTORY:
        rel_var_accum_bw.pop(0)

    dx_var_mean = sum(dx_var_accum_bw) / len(dx_var_accum_bw)
    dy_var_mean = sum(dy_var_accum_bw) / len(dy_var_accum_bw)
    rel_var_mean = sum(rel_var_accum_bw) / len(rel_var_accum_bw)
    print(f"[MotionModel][BW][AVG10] dx={dx_var_mean:.6f} dy={dy_var_mean:.6f} rel={rel_var_mean:.6f}")

    # Klassifikation 1:1 wie Forward
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
# Perspective-Erkennung (Mittelpunktanalyse) – rückwärts
# gleiche Logik wie Forward
# ==========================================================
def _detect_perspective_motion_backwards(
    marker_positions: dict[str, list[tuple[float, float]]],
    perspective_thresh: float = 0.002,
) -> tuple[str | None, float, dict[str, float]]:
    """
    Spiegel der vorwärts-Perspective-Analyse.
    Rückgabe: (center_marker, max_dev, per_marker_dev_dict)
    - center_marker: Name des Markers mit geringster Gesamtbewegung
    - max_dev: größte Abweichung ggü. Mittelwert der mv_i über alle Marker
    - per_marker_dev_dict: Abweichung je Marker (für per-Marker-Perspective)
    """

    if not marker_positions:
        return None, 0.0, {}

    # 1) Bewegungslänge pro Marker (mpd_i)
    total_movement: dict[str, float] = {}
    for name, positions in marker_positions.items():
        if len(positions) < 2:
            continue
        mpf_values = [(x + y) / 2.0 for x, y in positions]
        mpd_i = sum(abs(mpf_values[i + 1] - mpf_values[i]) for i in range(len(mpf_values) - 1))
        total_movement[name] = mpd_i

    if not total_movement:
        return None, 0.0, {}

    # 2) Mittelpunkt = Marker mit geringster Bewegung
    center_marker = min(total_movement, key=total_movement.get)
    center_positions = marker_positions[center_marker]
    mmx = sum(x for x, _ in center_positions) / len(center_positions)
    mmy = sum(y for _, y in center_positions) / len(center_positions)

    # 3) Abstände zum Mittelpunkt je Frame und deren Veränderung (mv_i)
    mv_values: dict[str, float] = {}
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
# Hauptlogik – Hybrid-Auswertung + Perspective – rückwärts
# ==========================================================
def get_from_selected_tracks_backwards(context: bpy.types.Context, max_frames: int = 10) -> None:
    """
    Rückwärts-Analyse:
    - verwendet dieselben Formeln & Threshold-Mappings wie Forward
    - eigene Akkumulatoren (…_bw)
    - schreibt in dieselben Scene-Keys (rot/scale/perspective-Thresholds)
    """
    
    global dx_var_accum_bw, dy_var_accum_bw, rel_var_accum_bw, global_p_dev_accum_bw

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
    # NOTE: get_positions() liefert vorwärts-sortierte Daten → für Backwards umkehren
    marker_positions: dict[str, list[tuple[float, float]]] = {}
    for track in selected_tracks:
        positions = get_positions(track, current_frame, max_frames=max_frames)
        positions = list(reversed(positions))  # <<< Backwards-Korrektur
        if len(positions) >= 2:
            marker_positions[track.name] = [(x, y) for _, (x, y) in positions]

    if not marker_positions:
        return

    try:
        # --- 1) Globales Modell aus Mittelwerten (autonom) ---
        all_positions: list[tuple[float, float]] = []
        for pts in marker_positions.values():
            mean_x = sum(x for x, _ in pts) / len(pts)
            mean_y = sum(y for _, y in pts) / len(pts)
            all_positions.append((mean_x, mean_y))

        global_model_bw = _evaluate_motion_model_pairwise_backwards(
            all_positions,
            getattr(scene, "kaiserlich_rot_thresh_x", 0.002),
            getattr(scene, "kaiserlich_scale_thresh_max", 0.005),
            getattr(scene, "kaiserlich_rot_scale_thresh_rot", 0.002),
            getattr(scene, "kaiserlich_rot_scale_thresh_scale", 0.005),
        )
        print(f"[MotionModel][BW] Global Model = {global_model_bw}")

        # --- 2) Perspective (gleiche Logik wie Forward) ---
        _, global_p_dev, _ = _detect_perspective_motion_backwards(
            marker_positions,
            getattr(scene, "kaiserlich_perspective_thresh", 0.002),
        )

        global_p_dev_accum_bw.append(global_p_dev)
        if len(global_p_dev_accum_bw) > MAX_HISTORY:
            global_p_dev_accum_bw.pop(0)

        global_p_dev_mean = (
            sum(global_p_dev_accum_bw) / len(global_p_dev_accum_bw)
            if global_p_dev_accum_bw
            else 0.0
        )
        print(f"[Perspective][BW][AVG10] global_p_dev={global_p_dev_mean:.6f}")

        # --- 3) Threshold-Kalibrierung (Formeln 1:1 wie Forward) ---
        dx_var_mean = sum(dx_var_accum_bw) / len(dx_var_accum_bw) if dx_var_accum_bw else 0.0
        dy_var_mean = sum(dy_var_accum_bw) / len(dy_var_accum_bw) if dy_var_accum_bw else 0.0
        rel_var_mean = sum(rel_var_accum_bw) / len(rel_var_accum_bw) if rel_var_accum_bw else 0.0

        scene["kaiserlich_rot_thresh_x"] = (dx_var_mean / 250.0) * 100000.0
        scene["kaiserlich_rot_thresh_y"] = (dy_var_mean / 250.0) * 100000.0
        scene["kaiserlich_scale_thresh_max"] = (rel_var_mean / 1000.0) * 100000.0
        scene["kaiserlich_scale_thresh_min"] = (rel_var_mean / 500.0) * 100000.0
        scene["kaiserlich_rot_scale_thresh_rot"] = (
            ((dx_var_mean / 250.0) + (dy_var_mean / 250.0)) / 2.0
        ) * 100000.0
        scene["kaiserlich_rot_scale_thresh_scale"] = (rel_var_mean / 750.0) * 100000.0
        scene["kaiserlich_perspective_thresh"] = (global_p_dev_mean / 10.0) * 1000000.0

    except Exception as e:
        print(f"[MotionModel][BW][ERROR] {e}")
        return

# ==========================================================
# Reset-Funktion für Backwards-Stats (symmetrisch zu Forward)
# ==========================================================
def reset_motion_average_backwards():
    dx_var_accum_bw.clear()
    dy_var_accum_bw.clear()
    rel_var_accum_bw.clear()
    global_p_dev_accum_bw.clear()
    print("[MotionModel][BW] Reset accumulators")
