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

def _evaluate_motion_model(marker_positions,
                           patches=None,
                           corr_values=None,
                           threshold_corr=0.85,
                           epsilon_affine=1e-3,
                           epsilon_rot=0.01,
                           epsilon_scale=0.02):
    """
    marker_positions: [(frame, x, y), ...]
    patches: optional list of (ndarray) image crops per frame
    corr_values: optional list of correlation floats
    """

    N = len(marker_positions)
    if N < 2:
        return "Loc"

    # ---------------------------------------------
    # Erweiterte Auswertung:
    # Prüft die RELATIONEN zwischen mehreren Markern.
    # Wenn die Distanzen konstant bleiben, aber die
    # Achsenverhältnisse (Δx/Δy) schwanken → Rotation.
    # ---------------------------------------------

    pts = np.array([[x, y] for _, x, y in marker_positions], dtype=np.float32)

    # Bewegungen pro Frame
    disp = np.diff(pts, axis=0)
    if len(disp) < 1:
        return "Loc"

    # Gesamtstrecke (Länge der Bewegungsvektoren)
    step_len = np.linalg.norm(disp, axis=1)
    mean_len = np.mean(step_len)

    # Varianz der Schrittweiten
    len_var = np.var(step_len)

    # Prüfe auf Richtungsänderungen: Differenz der Winkel zwischen den Schritten
    angles = np.arctan2(disp[:, 1], disp[:, 0])
    if len(angles) > 1:
        d_angle = np.diff(angles)
        mean_angle_change = np.mean(np.abs(d_angle))
    else:
        mean_angle_change = 0.0

    # Heuristik:
    # - kleine Winkeländerung → reine Translation
    # - größere Winkeländerung, aber konstante Länge → Rotation

    # relative Varianz als Maß für Skalierung
    rel_len_var = len_var / (mean_len**2 + 1e-9)

    # Neue Heuristik:
    # Wenn Abstände konstant bleiben, aber Verhältnis Δx/Δy stark schwankt → Rotation
    dx = disp[:, 0]
    dy = disp[:, 1]

    # Verhältnisänderung prüfen (wie sehr sich die Richtung zwischen Frames ändert)
    with np.errstate(divide='ignore', invalid='ignore'):
        xy_ratio = np.where(np.abs(dy) > 1e-9, dx / dy, 0)

    ratio_var = np.var(xy_ratio)

    # Entscheidung nach stabilen Relationen
    # ---------------------------------------------
    # Erweiterte Heuristik für Loc / LocRot:
    # Wenn die Distanz konstant bleibt, aber Δx und Δy sich
    # gegensinnig oder unterschiedlich stark verändern → Rotation.
    # ---------------------------------------------

    dx_var = np.var(dx)
    dy_var = np.var(dy)

    # Korrelation zwischen Δx und Δy: bei Translation meist ≈ +1,
    # bei Rotation ≈ -1 oder stark < +0.5
    if len(dx) > 2:
        corr = np.corrcoef(dx, dy)[0, 1]
    else:
        corr = 1.0

    # Debug-Ausgabe
    print(f"[EvalModel] rel_len_var={rel_len_var:.6f}, ratio_var={ratio_var:.6f}, dx_var={dx_var:.6f}, dy_var={dy_var:.6f}, corr={corr:.3f}")

    # Translation → beide Achsen variieren gleichgerichtet
    if rel_len_var < 0.001:
        if corr < 0.5 and (dx_var > 1e-6 or dy_var > 1e-6):
            model = "LocRot"
        else:
            model = "Loc"
    else:
        model = "Other"

    return model
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


def apply_formula_on_selected_tracks(context: bpy.types.Context, max_frames: int = 5) -> None:
    
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

    for track in selected_tracks:
        # Retrieve the marker positions for the most recent frames.
        positions = get_positions(track, current_frame, max_frames=max_frames)
        if len(positions) < 2:
            continue

        frames: List[int] = [frame for frame, _co in positions]
        xs: List[float] = [co[0] for _, co in positions]
        ys: List[float] = [co[1] for _, co in positions]

        # (Rohdaten-Logging entfernt – nur Ergebnis wird ausgegeben)

        # Fit linear models to x and y coordinates separately.
        intercept_x, slope_x = _linear_regression(frames, xs)
        intercept_y, slope_y = _linear_regression(frames, ys)

        modeled_positions: list[tuple[int, tuple[float, float]]] = []
        for f in frames:
            x_pred = intercept_x + slope_x * f
            y_pred = intercept_y + slope_y * f
            modeled_positions.append((f, (x_pred, y_pred)))

        # ============================================================
        # Bewegungsauswertung & Anwendung des Motion Models
        # ============================================================
        try:
            # Markerpositionen für Analyse sammeln
            marker_positions = [(f, x, y) for f, (x, y) in modeled_positions]

            # Bewegungsmodell bestimmen
            motion_model = _evaluate_motion_model(marker_positions)

            # Anwenden des erkannten Modells auf Track
            apply_motion_model(track, modeled_positions, motion_model=motion_model)

            # Logging / Debug-Ausgabe
            print(f"[FormulaHelper] {track.name}: detected {motion_model}")

        except Exception as e:
            print(f"[FormulaHelper] Fehler bei motion_model_eval für {track.name}: {e}")
            continue

        # Formel-Ergebnis-Log (Ausgabe der modellierten Werte)
        _emit_fit(
            track.name,
            frames,
            modeled_positions,
            intercept_x,
            slope_x,
            intercept_y,
            slope_y,
        )
