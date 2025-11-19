# Helper.validate_motion_backward_helper.py
from __future__ import annotations
import bpy
from typing import List

# ------------------------------------------------------------
# Hilfsfunktion: Marker-Positionen vorwärts holen
# ------------------------------------------------------------
def _get_positions_backward(track: bpy.types.MovieTrackingTrack,
                           current_frame: int,
                           max_frames: int = 4) -> List[tuple[int, tuple[float, float]]]:

    positions = []
    markers = track.markers
    end = current_frame + max_frames

    for frame in range(current_frame, end + 1):
        marker = markers.find_frame(frame, exact=True)
        if marker and marker.co:
            positions.append((frame, marker.co.copy()))
    return positions


# ------------------------------------------------------------
# Haupt-Helper (Forward-Motion-Check für Backward-Tracking)
# ------------------------------------------------------------
def validate_calibrate_tracks_backward_window(context: bpy.types.Context) -> None:
    scene = context.scene
    clip = getattr(context.space_data, "clip", None)
    if clip is None:
        print("[ValidateForwardMotion] Kein Clip gefunden.")
        return

    # --------------------------------------------------------
    # Check: Existenz der Referenz-Listen
    # --------------------------------------------------------
    good = getattr(scene, "good_tracks", "")
    best = getattr(scene, "best_tracks", "")

    if not good and not best:
        print("[ValidateForwardMotion] Keine good/best Tracks → Abbruch.")
        return

    ref_list = best if best else good
    ref_list = [name.strip() for name in ref_list.split(",") if name.strip()]

    calibrate_list = getattr(scene, "calibrate_tracks", "")
    if not calibrate_list:
        print("[ValidateForwardMotion] Keine calibrate_tracks → Abbruch.")
        return
    calibrate_list = [name.strip() for name in calibrate_list.split(",") if name.strip()]

    # --------------------------------------------------------
    # Δ-Vektoren aus Referenz (Best/Good), aber rückwärts interpretiert
    # (Frame+N → Frame), damit backward-Tracker valide bleibt
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

        # Erstes ist Zukunft (Frame+n), zweites Zukunft früher (Frame+n+1)
        (_, (x_future, y_future)), (_, (x_future2, y_future2)) = pos[0], pos[1]

        # Rückwärts-Richtung: Δ = (Frame+n) − (Frame+n+1)
        dx_values.append(x_future - x_future2)
        dy_values.append(y_future - y_future2)

    if not dx_values or not dy_values:
        print("[ValidateForwardMotion] Keine gültigen Bewegungsvektoren.")
        return

    avg_dx = sum(dx_values) / len(dx_values)
    avg_dy = sum(dy_values) / len(dy_values)

    print(f"[Reference Δ FW] avg_dx={avg_dx:.6f}, avg_dy={avg_dy:.6f}")

    # --------------------------------------------------------
    # Threshold in Prozent
    # --------------------------------------------------------
    max_dev = getattr(scene, "max_error_value", 5.0) / 100.0

    # --------------------------------------------------------
    # Calibrate-Tracks prüfen und ggf. muten
    # --------------------------------------------------------
    for name in calibrate_list:
        track = clip.tracking.tracks.get(name)
        if not track:
            continue

        pos = _get_positions_backward(track, current_frame, 4)
        if len(pos) < 2:
            continue

        (_, (x_future, y_future)), (_, (x_future2, y_future2)) = pos[0], pos[1]
        dx = x_future - x_future2
        dy = y_future - y_future2

        dev_x = abs(dx - avg_dx)
        dev_y = abs(dy - avg_dy)

        print(f"[Check FW {name}] Δx={dx:.6f} Δy={dy:.6f} | DevX={dev_x:.6f}, DevY={dev_y:.6f}")

        if dev_x > max_dev or dev_y > max_dev:
            marker = track.markers.find_frame(current_frame, exact=True)
            if marker:
                marker.mute = True
                print(f" → [MUTED FW @ {current_frame}] Track {name} (abweichend!)")


# ------------------------------------------------------------
# Aufruf-Beispiel in einem Operator:
# validate_calibrate_tracks_backward_window(context)
# ------------------------------------------------------------
