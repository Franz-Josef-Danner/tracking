# Helper/formula_helper.py
from __future__ import annotations

import bpy
from typing import List, Tuple
import math

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
        # relative Distanz nach deiner Vorgabe
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

def _resolve_transformed_thresholds(scene: bpy.types.Scene) -> tuple[float, float, float, float, float]:
    """Berechnet die transformierten Threshold-Werte für Tracking."""

    # Globaler MAX-Normierungswert aus motion_average
    inv = float(scene.get("kaiserlich_threshold_inv", 1.0))
    if inv == 0.0:
        inv = 1.0

    # Rot-Threshold jetzt gegen die globale MAX-Normierung skalieren
    rot = getattr(scene, "kaiserlich_rot_thresh_x", 0.002) / inv
    scale = (1 - getattr(scene, "kaiserlich_scale_thresh_max", 0.005)) / inv
    rot_scale_rot = (1 - getattr(scene, "kaiserlich_rot_scale_thresh_rot", 0.002)) / inv
    rot_scale_scale = (1 - getattr(scene, "kaiserlich_rot_scale_thresh_scale", 0.005)) / inv
    perspective = (1 - getattr(scene, "kaiserlich_perspective_thresh", 0.002)) / inv
    return rot, scale, rot_scale_rot, rot_scale_scale, perspective




# ==========================================================
# Hauptlogik – Hybrid-Auswertung + Perspective
# ==========================================================

def apply_formula_on_selected_tracks(context: bpy.types.Context, max_frames: int = 10) -> None:
    """Analysiert Markerbewegung rückwärts und setzt Motion Model (Loc / LocRot / LocScale / LocRotScale / Perspective)."""
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

    # Thresholds zentral berechnen
    rot, scale, r_rot, r_scale, p_thresh = _resolve_transformed_thresholds(scene)

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
            rot,
            scale,
            r_rot,
            r_scale
        )

        # --- 2) Perspective global & per Marker ---
        _, global_p_dev, per_marker_dev = _detect_perspective_motion(
            marker_positions,
            p_thresh
        )

        if global_p_dev > p_thresh:
            global_model = "Perspective"

        # --- 3) Pro Track anwenden ---
        for track in selected_tracks:
            positions = get_positions(track, current_frame, max_frames=max_frames)
            if len(positions) < 2:
                continue

            marker_p_dev = per_marker_dev.get(track.name, 0.0)

            # Perspective hat Priorität
            if global_model == "Perspective" or marker_p_dev > p_thresh:
                motion_model = "Perspective"
            else:
                # Pairwise für individuellen Marker
                individual_model = _evaluate_motion_model_pairwise(
                    [(x, y) for _, (x, y) in positions],
                    rot,
                    scale,
                    r_rot,
                    r_scale
                )

                # Hybrid-Regel
                motion_model = individual_model if individual_model != global_model else global_model

            apply_motion_model(track, positions, motion_model=motion_model)

    except Exception:
        pass
