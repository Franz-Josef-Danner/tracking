# Helper.motion_average_backwards.py
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


def _evaluate_motion_model_pairwise_backwards(all_positions: list[tuple[float, float]],
                                    thresh_rot: float = 0.002,
                                    thresh_scale: float = 0.005,
                                    thresh_rot_scale_rot: float = 0.002,
                                    thresh_rot_scale_scale: float = 0.005) -> str:
    global dx_var_accum, dy_var_accum, rel_var_accum, MAX_HISTORY

    if len(all_positions) < 2:
        return "Loc"

    # BACKWARD-Variante: von hinten nach vorne auswerten
    avg_x_values = []
    avg_y_values = []
    rel_distances = []

    for i in range(len(all_positions) - 1, 0, -1):
        (x1, y1) = all_positions[i]      # aktueller (späterer) Frame
        (x2, y2) = all_positions[i - 1]  # vorheriger Frame in der Zeit

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
    print(f"[MotionModel][AVG10] dx={dx_var_mean:.6f} dy={dy_var_mean:.6f} rel={rel_var_mean:.6f}")

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

def _detect_perspective_motion_backwards(marker_positions: dict[str, list[tuple[float, float]]],
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
        # Rückwärts-Tracking: absolute Differenzen nutzen
        # damit Vorzeichen-Flip keine Erkennung verhindert
        md_list = [(abs(mmx - x) + abs(mmy - y)) / 2.0 for x, y in positions]
        abs_dev = [abs(md_list[i] - md_list[i + 1]) for i in range(len(md_list) - 1)]
        mv_i = sum(abs_dev)
        mv_values[name] = mv_i
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

def get_from_selected_tracks_backwards(context: bpy.types.Context, max_frames: int = 10) -> None:
    global dx_var_accum, dy_var_accum, rel_var_accum, global_p_dev_accum, MAX_HISTORY
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
        # Rückwärts-Tracking: Reihenfolge der Positionen umkehren
        if len(positions) >= 2:
            pts = [(x, y) for _, (x, y) in positions]
            pts = list(reversed(pts))
            marker_positions[track.name] = pts
    if not marker_positions:
        return

    try:
        # --- 1) Globales Modell aus Mittelwerten ---
        all_positions = []
        for pts in marker_positions.values():
            mean_x = sum(x for x, _ in pts) / len(pts)
            mean_y = sum(y for _, y in pts) / len(pts)
            all_positions.append((mean_x, mean_y))

        global_model = _evaluate_motion_model_pairwise_backwards(
            all_positions,
            getattr(scene, "kaiserlich_rot_thresh_x", 0.002),
            getattr(scene, "kaiserlich_scale_thresh_max", 0.005),
            getattr(scene, "kaiserlich_rot_scale_thresh_rot", 0.002),
            getattr(scene, "kaiserlich_rot_scale_thresh_scale", 0.005)
        )

        # --- 2) Perspective global & per Marker einmalig berechnen ---
        _, global_p_dev, per_marker_dev = _detect_perspective_motion_backwards(
            marker_positions,
            getattr(scene, "kaiserlich_perspective_thresh", 0.002)
        )
        perspective_thresh = getattr(scene, "kaiserlich_perspective_thresh", 0.002)
        
        global_p_dev_accum.append(global_p_dev)
        if len(global_p_dev_accum) > MAX_HISTORY: global_p_dev_accum.pop(0)
        global_p_dev_accum_mean = sum(global_p_dev_accum) / len(global_p_dev_accum)
        print(f"[Perspective][AVG10] global_p_dev={global_p_dev_accum_mean:.6f}")

        dx_var_mean = sum(dx_var_accum) / len(dx_var_accum) if dx_var_accum else 0.0
        dy_var_mean = sum(dy_var_accum) / len(dy_var_accum) if dy_var_accum else 0.0
        rel_var_mean = sum(rel_var_accum) / len(rel_var_accum) if rel_var_accum else 0.0

        # --- Adaptive Threshold Stabilisierung (Backward-Mode)
        MIN_ROT = 0.0005
        MIN_SCALE = 0.0010
        MIN_PERSPECTIVE = 0.0001
        STABILITY_FACTOR = 0.2  # max 20% Änderung pro Schritt

        def _clamp_adapt(prev, new, min_val):
            if prev is None:
                return max(new, min_val)
            # Hysterese: begrenze Änderungsrate
            delta = prev * STABILITY_FACTOR
            return max(min(prev + delta, new), max(prev - delta, min_val))

        # aktuelle Szene-Thresholds
        rot_prev = getattr(scene, "kaiserlich_rot_thresh_x", MIN_ROT)
        scale_prev = getattr(scene, "kaiserlich_scale_thresh_max", MIN_SCALE)
        persp_prev = getattr(scene, "kaiserlich_perspective_thresh", MIN_PERSPECTIVE)

        # neue Vorschlagswerte aus Varianzen
        rot_new = max(dx_var_mean, dy_var_mean)
        scale_new = rel_var_mean
        persp_new = global_p_dev_accum_mean

        # stabilisierte Thresholds
        scene["kaiserlich_rot_thresh_x"] = _clamp_adapt(rot_prev, rot_new, MIN_ROT)
        scene["kaiserlich_rot_thresh_y"] = scene["kaiserlich_rot_thresh_x"]
        scene["kaiserlich_scale_thresh_max"] = _clamp_adapt(scale_prev, scale_new, MIN_SCALE)
        scene["kaiserlich_rot_scale_thresh_rot"] = scene["kaiserlich_rot_thresh_x"]
        scene["kaiserlich_rot_scale_thresh_scale"] = scene["kaiserlich_scale_thresh_max"]
        scene["kaiserlich_perspective_thresh"] = _clamp_adapt(persp_prev, persp_new, MIN_PERSPECTIVE)

        print(f"[STABILIZED] Rot={scene['kaiserlich_rot_thresh_x']:.6f} "
            f"Scale={scene['kaiserlich_scale_thresh_max']:.6f} "
            f"Persp={scene['kaiserlich_perspective_thresh']:.6f}")



    except Exception:
        pass
