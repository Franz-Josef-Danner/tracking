from __future__ import annotations

import bpy
import logging
from typing import List, Tuple
import numpy as np
import cv2

from .marker_positions_helper import get_positions
from .motion_model_helper import apply_motion_model


# ==========================================================
# Bewegungsmodell-Evaluierung (integriert)
# ==========================================================

def _evaluate_motion_model_pairwise(marker_positions, thresh_x=0.001, thresh_y=0.001):
    """
    Bestimmt das Bewegungsmodell anhand paarweiser Marker-Vergleiche.
    marker_positions: dict[str, list[tuple[x, y]]]
        z. B. {"Track.001": [(x1, y1), (x2, y2), ...], "Track.002": [...], ...}
    """
    markers = list(marker_positions.keys())
    if len(markers) < 2:
        return "Loc"

    total_dev_x = 0.0
    total_dev_y = 0.0
    total_dev_pos = 0.0
    pair_count = 0

    for i in range(len(markers)):
        for j in range(i + 1, len(markers)):
            mi = marker_positions[markers[i]]
            mj = marker_positions[markers[j]]
            if len(mi) != len(mj):
                continue

            avg_x_values = []
            avg_y_values = []
            avg_pos_values = []

            for f in range(len(mi)):
                m1x, m1y = mi[f]
                m2x, m2y = mj[f]
                avg_x = (m1x + m2x) / 2.0
                avg_y = (m1y + m2y) / 2.0
                avg_pos = (m1x + m2x + m1y + m2y) / 4.0
                avg_x_values.append(avg_x)
                avg_y_values.append(avg_y)
                avg_pos_values.append(avg_pos)

            # Abweichungen über die Zeit
            dx_var = max(avg_x_values) - min(avg_x_values)
            dy_var = max(avg_y_values) - min(avg_y_values)
            pos_var = max(avg_pos_values) - min(avg_pos_values)

            total_dev_x += dx_var
            total_dev_y += dy_var
            total_dev_pos += pos_var
            pair_count += 1

    if pair_count == 0:
        return "Loc"

    mean_dev_x = total_dev_x / pair_count
    mean_dev_y = total_dev_y / pair_count
    mean_dev_pos = total_dev_pos / pair_count

    print(f"[EvalPairwise] mean_dev_pos={mean_dev_pos:.6f}, mean_dev_x={mean_dev_x:.6f}, mean_dev_y={mean_dev_y:.6f}, "
          f"thresh_x={thresh_x:.6f}, thresh_y={thresh_y:.6f}")


    print(f"[EvalPairwise] mean_dev_pos={mean_dev_pos:.6f}, mean_dev_x={mean_dev_x:.6f}, mean_dev_y={mean_dev_y:.6f}, "
          f"thresh_x={thresh_x:.6f}, thresh_y={thresh_y:.6f}")

    # Klassifikation mit dynamischer Toleranz
    if mean_dev_pos < thresh_x * 2 and (mean_dev_x > thresh_x or mean_dev_y > thresh_y):
        return "LocRot"
    elif mean_dev_pos < thresh_x * 4 and (mean_dev_x > thresh_x * 2 or mean_dev_y > thresh_y * 2):
        return "LocRot"
    else:
        return "Loc"
      
def _estimate_affine_from_points(pts):
    """Fallback: einfache Translation aus Start- und Endpunkt."""
    if len(pts) < 2:
        return np.eye(3, dtype=np.float32)
    p0, p1 = pts[0], pts[-1]
    dx, dy = p1 - p0
    H = np.eye(3, dtype=np.float32)
    H[0, 2] = dx
    H[1, 2] = dy
    return H



# Globaler Schalter zum schnellen (De-)Aktivieren der Glättung.
# Auf False setzen um die Funktion wirkungslos zu machen (für Vergleichstests).
ENABLE_FORMULA_SMOOTHING = True

# Minimaler Logger für Formel-Ergebnis-Ausgaben (Fallback auf print)
logger = logging.getLogger(__name__)

def _emit_fit(track_name: str,
              frames: list[int],
              modeled_positions: list[tuple[int, tuple[float, float]]],
              intercept_x: float, slope_x: float,
              intercept_y: float, slope_y: float) -> None:
    """Ausgabe der berechneten Modellwerte für einen Track.

    Format Beispiel:
    FIT Track01 ix=0.123456 sx=0.000321 iy=0.456789 sy=-0.000210 positions: 120:0.52310,0.41234 121:0.52342,0.41228
    """
    pos_parts = [f"{f}:{x:.5f},{y:.5f}" for f, (x, y) in modeled_positions]
    line = (
        f"FIT {track_name} "
        f"ix={intercept_x:.6f} sx={slope_x:.6f} "
        f"iy={intercept_y:.6f} sy={slope_y:.6f} "
        f"frames={frames[0]}..{frames[-1]} n={len(frames)} positions: " + " ".join(pos_parts)
    )
    if logger.hasHandlers() and logger.isEnabledFor(logging.INFO):
        logger.info(line)
    else:
        print(line)


def _linear_regression(frames: List[int], values: List[float]) -> Tuple[float, float]:
    """Compute slope and intercept for a simple linear regression.

    Parameters
    ----------
    frames : List[int]
        The independent variable values (frame numbers).
    values : List[float]
        The dependent variable values (x or y coordinates).

    Returns
    -------
    Tuple[float, float]
        A tuple ``(intercept, slope)`` representing the parameters of
        the fitted line ``value = intercept + slope * frame``.
    """
    n = len(frames)
    if n == 0:
        return 0.0, 0.0
    f_avg = sum(frames) / n
    v_avg = sum(values) / n
    denom = sum((f - f_avg) ** 2 for f in frames)
    # Avoid division by zero; if all frames are identical, slope = 0.
    if denom == 0.0:
        return v_avg, 0.0
    slope = sum((f - f_avg) * (v - v_avg) for f, v in zip(frames, values)) / denom
    intercept = v_avg - slope * f_avg
    return intercept, slope


def apply_formula_on_selected_tracks(context: bpy.types.Context, max_frames: int = 10) -> None:
    
    if not ENABLE_FORMULA_SMOOTHING:
        return

    scene = context.scene
    clip = getattr(context.space_data, "clip", None)
    if clip is None:
        return

    # Determine which tracks to process: all selected tracks, or the
    # active track if none are selected.  ``track.select`` is True
    # when the track is selected in the UI【646072811079919†L2272-L2278】.
    selected_tracks = [t for t in clip.tracking.tracks if t.select]
    if not selected_tracks:
        active_track = clip.tracking.tracks.active
        if active_track:
            selected_tracks = [active_track]

    current_frame = scene.frame_current

    if not selected_tracks:
        return

    # ============================================================
    # Gemeinsame Bewegungsauswertung aller ausgewählten Tracks
    # ============================================================

    marker_positions = {}
    for track in selected_tracks:
        positions = get_positions(track, current_frame, max_frames=max_frames)
        if len(positions) < 2:
            continue
        marker_positions[track.name] = [(x, y) for _, (x, y) in positions]

    if len(marker_positions) < 2:
        print("[FormulaHelper] Zu wenige Marker für Paarvergleich – nur Loc möglich.")
        return

    try:
        # Bewegungsmodell anhand aller Markerpaare bestimmen
        motion_model = _evaluate_motion_model_pairwise(
            marker_positions,
            scene.kaiserlich_rot_thresh_x,
            scene.kaiserlich_rot_thresh_y
        )

        print(f"[FormulaHelper] Gemeinsames Modell erkannt: {motion_model}")

        # Für jedes Track individuell Regression anwenden und Modell setzen
        for track in selected_tracks:
            positions = get_positions(track, current_frame, max_frames=max_frames)
            frames: List[int] = [frame for frame, _co in positions]
            xs: List[float] = [co[0] for _, co in positions]
            ys: List[float] = [co[1] for _, co in positions]

            intercept_x, slope_x = _linear_regression(frames, xs)
            intercept_y, slope_y = _linear_regression(frames, ys)

            modeled_positions: list[tuple[int, tuple[float, float]]] = []
            for f in frames:
                x_pred = intercept_x + slope_x * f
                y_pred = intercept_y + slope_y * f
                modeled_positions.append((f, (x_pred, y_pred)))

            # Motion Model anwenden
            apply_motion_model(track, modeled_positions, motion_model=motion_model)

            # Log / Debug
            print(f"[FormulaHelper] {track.name}: detected {motion_model}")

            _emit_fit(
                track.name,
                frames,
                modeled_positions,
                intercept_x,
                slope_x,
                intercept_y,
                slope_y,
            )

    except Exception as e:
        print(f"[FormulaHelper] Fehler bei gemeinsamer motion_model_eval: {e}")
        return

