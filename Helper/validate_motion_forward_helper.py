# Helper.validate_motion_forward_helper.py
from __future__ import annotations
import bpy
from typing import List, Tuple, Optional

# ------------------------------------------------------------
# Hilfsfunktion: Marker-Positionen rückwärts holen
# ------------------------------------------------------------
def _get_positions_backward(track: bpy.types.MovieTrackingTrack,
                            current_frame: int,
                            max_frames: int = 4) -> List[tuple[int, tuple[float, float]]]:

    positions = []
    markers = track.markers
    start = current_frame - max_frames

    for frame in range(current_frame, start - 1, -1):
        marker = markers.find_frame(frame, exact=True)
        if marker and marker.co:
            positions.append((frame, marker.co.copy()))

    return positions


# ------------------------------------------------------------
# Haupt-Helper
# ------------------------------------------------------------
def validate_calibrate_tracks_against_motion(context: bpy.types.Context) -> None:
    scene = context.scene
    clip = getattr(context.space_data, "clip", None)
    if clip is None:
        print("[ValidateMotion] Kein Clip gefunden.")
        return

    # --------------------------------------------------------
    # Check: Existenz der Referenz-Listen
    # --------------------------------------------------------
    good = getattr(scene, "good_tracks", "")
    best = getattr(scene, "best_tracks", "")

    if not good and not best:
        print("[ValidateMotion] Keine good/best-Tracks vorhanden → Abbruch.")
        return

    # Priorität: best_tracks > good_tracks
    ref_list = best if best else good
    ref_list = [name.strip() for name in ref_list.split(",") if name.strip()]

    # Calibrate Tracks
    calibrate_list = getattr(scene, "calibrate_tracks", "")
    if not calibrate_list:
        print("[ValidateMotion] Keine calibrate_tracks vorhanden → Abbruch.")
        return
    calibrate_list = [name.strip() for name in calibrate_list.split(",") if name.strip()]

    # --------------------------------------------------------
    # Δ-Vektoren aus best/good Tracks berechnen
    # --------------------------------------------------------
    current_frame = scene.frame_current
    dx_values, dy_values = [], []

    for name in ref_list:
        track = clip.tracking.tracks.get(name)
        if not track:
            continue

        pos = _get_positions_backward(track, current_frame, 4)
        if len(pos) < 2:
            continue

        (_, (x1, y1)), (_, (x2, y2)) = pos[0], pos[1]
        dx_values.append(x1 - x2)
        dy_values.append(y1 - y2)

    if not dx_values or not dy_values:
        print("[ValidateMotion] Keine gültigen Bewegungsvektoren der Referenztracks.")
        return

    avg_dx = sum(dx_values) / len(dx_values)
    avg_dy = sum(dy_values) / len(dy_values)

    print(f"[Reference Δ] avg_dx={avg_dx:.6f}, avg_dy={avg_dy:.6f}")

    # --------------------------------------------------------
    # Threshold (in Prozent konvertiert)
    # --------------------------------------------------------
    max_dev = getattr(scene, "max_error_value", 5.0) / 100.0

    # --------------------------------------------------------
    # Calibrate-Tracks gegen Durchschnitt prüfen und ggf. muten
    # --------------------------------------------------------
    for name in calibrate_list:
        track = clip.tracking.tracks.get(name)
        if not track:
            continue

        pos = _get_positions_backward(track, current_frame, 4)
        if len(pos) < 2:
            continue

        (_, (x1, y1)), (_, (x2, y2)) = pos[0], pos[1]
        dx = x1 - x2
        dy = y1 - y2

        dev_x = abs(dx - avg_dx)
        dev_y = abs(dy - avg_dy)

        print(f"[Check {name}] Δx={dx:.6f} Δy={dy:.6f} | DevX={dev_x:.6f}, DevY={dev_y:.6f}")

        if dev_x > max_dev or dev_y > max_dev:
            marker = track.markers.find_frame(current_frame, exact=True)
            if marker:
                marker.mute = True  # kein weiteres Tracking
                print(f" → [MUTED @ {current_frame}] Track {name} (abweichend!)")


# ------------------------------------------------------------
# Aufruf-Beispiel aus einem Operator:
# validate_calibrate_tracks_against_motion(context)
# ------------------------------------------------------------
