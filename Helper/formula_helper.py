from __future__ import annotations

import bpy
import logging
from typing import List, Tuple
import numpy as np
import traceback

from .marker_positions_helper import get_positions
from .motion_model_helper import apply_motion_model

# ==========================================================
# Bewegungsmodell-Evaluierung (integriert)
# ==========================================================

def _evaluate_motion_model_pairwise(all_positions: list[tuple[float, float]],
                                    thresh_rot: float = 0.002,
                                    thresh_locrot: float = 0.01) -> str:
    """
    Bestimmt das Bewegungsmodell anhand paarweiser Vergleiche der Markerpositionen.
    Für Testzwecke werden nur zwei Modelle unterschieden: Loc und LocRot.
    """
    if len(all_positions) < 2:
        print("[EvalPairwise] Zu wenige Marker – return Loc")
        return "Loc"

    diffs = []
    for i in range(len(all_positions) - 1):
        (x1, y1), (x2, y2) = all_positions[i], all_positions[i + 1]
        diffs.append(((x2 - x1), (y2 - y1)))

    if not diffs:
        print("[EvalPairwise] Keine gültigen Differenzen – return Loc")
        return "Loc"

    mean_dx = sum(abs(dx) for dx, _ in diffs) / len(diffs)
    mean_dy = sum(abs(dy) for _, dy in diffs) / len(diffs)
    dev_xy = abs(mean_dx - mean_dy)

    print(f"[EvalPairwise] mean_dx={mean_dx:.5f}, mean_dy={mean_dy:.5f}, dev_xy={dev_xy:.5f}")

    # Nur Loc und LocRot zulassen
    if dev_xy < thresh_rot:
        return "Loc"
    else:
        return "LocRot"


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
ENABLE_FORMULA_SMOOTHING = True
logger = logging.getLogger(__name__)

def _emit_fit(track_name: str,
              frames: list[int],
              modeled_positions: list[tuple[int, tuple[float, float]]],
              intercept_x: float, slope_x: float,
              intercept_y: float, slope_y: float) -> None:
    """Ausgabe der berechneten Modellwerte für einen Track."""
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
    """Compute slope and intercept for a simple linear regression."""
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


def apply_formula_on_selected_tracks(context: bpy.types.Context, max_frames: int = 10) -> None:
    """Analysiert die Markerbewegung und setzt das passende Motion Model (nur Loc / LocRot)."""
    
    if not ENABLE_FORMULA_SMOOTHING:
        print("[FormulaHelper] Glättung deaktiviert – überspringe.")
        return

    scene = context.scene
    clip = getattr(context.space_data, "clip", None)
    if clip is None:
        print("[FormulaHelper] Kein aktiver Clip gefunden.")
        return

    selected_tracks = [t for t in clip.tracking.tracks if t.select]
    if not selected_tracks:
        active_track = clip.tracking.tracks.active
        if active_track:
            selected_tracks = [active_track]

    if not selected_tracks:
        print("[FormulaHelper] Keine Tracks ausgewählt.")
        return

    current_frame = scene.frame_current

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
        all_positions = []
        for pts in marker_positions.values():
            if not pts:
                continue
            mean_x = sum(x for x, _ in pts) / len(pts)
            mean_y = sum(y for _, y in pts) / len(pts)
            all_positions.append((mean_x, mean_y))

        motion_model = _evaluate_motion_model_pairwise(
            all_positions,
            getattr(scene, "kaiserlich_rot_thresh_x", 0.002),
            getattr(scene, "kaiserlich_rot_thresh_y", 0.01)
        )

        print(f"[FormulaHelper] Gemeinsames Modell erkannt: {motion_model}")

        for track in selected_tracks:
            positions = get_positions(track, current_frame, max_frames=max_frames)
            if len(positions) < 2:
                continue

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

            apply_motion_model(track, modeled_positions, motion_model=motion_model)
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
        print("[FormulaHelper] *** motion_model_eval Exception ***")
        print(f"Type: {type(e).__name__}, Message: {e}")
        print(traceback.format_exc())
        return
