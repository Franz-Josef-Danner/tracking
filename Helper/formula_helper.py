from __future__ import annotations

import bpy
from typing import List, Tuple
import numpy as np
import math
import traceback

from .marker_positions_helper import get_positions
from .motion_model_helper import apply_motion_model


# ==========================================================
# Bewegungsmodell-Evaluierung (Loc, LocRot, LocScale, LocRotScale)
# ==========================================================

def _evaluate_motion_model_pairwise(all_positions: list[tuple[float, float]],
                                    thresh_rot: float = 0.002,
                                    thresh_scale: float = 0.005,
                                    thresh_rot_scale_rot: float = 0.002,
                                    thresh_rot_scale_scale: float = 0.005) -> str:
    """Bestimmt das Bewegungsmodell anhand paarweiser Vergleiche der Markerpositionen."""
    if len(all_positions) < 2:
        return "Loc"

    rel_distances = []
    avg_x_values = []
    avg_y_values = []

    for i in range(len(all_positions) - 1):
        (x1, y1), (x2, y2) = all_positions[i], all_positions[i + 1]
        avg_x = (x1 + x2) / 2.0
        avg_y = (y1 + y2) / 2.0
        rel_dist = (abs(x1 - x2) + abs(y1 - y2)) / 2.0
        avg_x_values.append(avg_x)
        avg_y_values.append(avg_y)
        rel_distances.append(rel_dist)

    if not rel_distances:
        return "Loc"

    dx_var = max(avg_x_values) - min(avg_x_values)
    dy_var = max(avg_y_values) - min(avg_y_values)
    rel_var = max(rel_distances) - min(rel_distances)

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
                               perspective_thresh: float = 0.002) -> tuple[str | None, float]:
    """Bestimmt Mittelpunkt-Marker und prüft perspektivische Abweichung."""
    if not marker_positions:
        return None, 0.0

    # 1. Bewegungslänge pro Marker (mpd_i)
    total_movement = {}
    for name, positions in marker_positions.items():
        if len(positions) < 2:
            continue
        mpf_values = [(x + y) / 2.0 for x, y in positions]
        mpd_i = sum(abs(mpf_values[i+1] - mpf_values[i]) for i in range(len(mpf_values) - 1))
        total_movement[name] = mpd_i

    if not total_movement:
        return None, 0.0

    # 2. Mittelpunkt = Marker mit geringster Bewegung
    center_marker = min(total_movement, key=total_movement.get)
    center_positions = marker_positions[center_marker]
    mmx = sum(x for x, _ in center_positions) / len(center_positions)
    mmy = sum(y for _, y in center_positions) / len(center_positions)

    # 3. Abstände zum Mittelpunkt & Veränderung (mv_i)
    mv_values = {}
    for name, positions in marker_positions.items():
        md_list = [(abs(mmx - x) + abs(mmy - y)) / 2.0 for x, y in positions]
        mv_i = sum(md_list[i] - md_list[i + 1] for i in range(len(md_list) - 1))
        mv_values[name] = mv_i

    mvth = sum(abs(v) for v in mv_values.values()) / len(mv_values)

    # 4. Abweichung prüfen
    max_dev = 0.0
    for mv_i in mv_values.values():
        mvc_i = abs(mv_i - mvth)
        max_dev = max(max_dev, mvc_i)

    if max_dev > perspective_thresh:
        print(f"[FormulaHelper] Perspective erkannt (Abweichung {max_dev:.6f})")
        return center_marker, max_dev

    return center_marker, 0.0


# ==========================================================
# Logging-Funktion
# ==========================================================

def _emit_fit(track_name: str, motion_model: str) -> None:
    print(f"[FormulaHelper] {track_name}: {motion_model}")


# ==========================================================
# Hilfsfunktionen
# ==========================================================

def _linear_regression(frames: List[int], values: List[float]) -> Tuple[float, float]:
    n = len(frames)
    if n == 0:
        return 0.0, 0.0
    f_avg = sum(frames) / n
    v_avg = sum(values) / n
    denom = sum((f - f_avg) ** 2 for f in frames)
    if denom == 0.0:
        return v_avg, 0.0
    slope = sum((f - f_avg) * (v - v_avg) for f, v in zip(frames, values)) / denom
    intercept = v_avg - slope * f_avg
    return intercept, slope


# ==========================================================
# Hauptlogik – Hybrid-Auswertung + Perspective
# ==========================================================

def apply_formula_on_selected_tracks(context: bpy.types.Context, max_frames: int = 10) -> None:
    """Analysiert Markerbewegung und setzt Motion Model (Loc / LocRot / LocScale / LocRotScale / Perspective)."""
    clip = getattr(context.space_data, "clip", None)
    if clip is None:
        return

    scene = context.scene
    selected_tracks = [t for t in clip.tracking.tracks if t.select]
    if not selected_tracks:
        active_track = clip.tracking.tracks.active
        if active_track:
            selected_tracks = [active_track]
    if not selected_tracks:
        return

    current_frame = scene.frame_current

    # --- Markerpositionen sammeln ---
    marker_positions = {}
    for track in selected_tracks:
        positions = get_positions(track, current_frame, max_frames=max_frames)
        if len(positions) >= 2:
            marker_positions[track.name] = [(x, y) for _, (x, y) in positions]

    # --- 1. Globales Modell ---
    try:
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


        # --- 2. Perspektive prüfen (global)
        _, perspective_dev = _detect_perspective_motion(
            marker_positions,
            getattr(scene, "kaiserlich_perspective_thresh", 0.002)
        )
        if perspective_dev > getattr(scene, "kaiserlich_perspective_thresh", 0.002):
            global_model = "Perspective"

        # --- 3. Pro Track anwenden ---
        for track in selected_tracks:
            positions = get_positions(track, current_frame, max_frames=max_frames)
            if len(positions) < 2:
                continue
        
            # Basisbewertung
            individual_model = _evaluate_motion_model_pairwise(
                [(x, y) for _, (x, y) in positions],
                getattr(scene, "kaiserlich_rot_thresh_x", 0.002),
                getattr(scene, "kaiserlich_scale_thresh_max", 0.005),
                getattr(scene, "kaiserlich_rot_scale_thresh_rot", 0.002),
                getattr(scene, "kaiserlich_rot_scale_thresh_scale", 0.005)
            )
        
            # Perspektive separat prüfen (danach Priorität)
            _, p_dev_single = _detect_perspective_motion(
                {track.name: [(x, y) for _, (x, y) in positions]},
                getattr(scene, "kaiserlich_perspective_thresh", 0.002)
            )
        
            if p_dev_single > getattr(scene, "kaiserlich_perspective_thresh", 0.002):
                individual_model = "Perspective"
        
            # Kombinierte Entscheidung
            motion_model = "Perspective" if global_model == "Perspective" or individual_model == "Perspective" else individual_model


            motion_model = individual_model if individual_model != global_model else global_model

            frames = [frame for frame, _ in positions]
            xs = [co[0] for _, co in positions]
            ys = [co[1] for _, co in positions]

            intercept_x, slope_x = _linear_regression(frames, xs)
            intercept_y, slope_y = _linear_regression(frames, ys)

            modeled_positions = [(f, (intercept_x + slope_x * f, intercept_y + slope_y * f))
                                 for f in frames]

            apply_motion_model(track, modeled_positions, motion_model=motion_model)
            _emit_fit(track.name, motion_model)

    except Exception as e:
        print(f"[FormulaHelper] Fehler: {e}")
        print(traceback.format_exc())
