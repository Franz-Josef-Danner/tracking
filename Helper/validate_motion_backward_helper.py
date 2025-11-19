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
# Hilfsfunktionen zum Laden der Track-Namen
# ------------------------------------------------------------
def _resolve_reference_track_names(scene: bpy.types.Scene) -> List[str]:
    """Lädt best_tracks_names > good_tracks_names, gefiltert auf Strings."""
    if scene.get("best_tracks"):
        names = scene.get("best_tracks_names", [])
        return [n for n in names if isinstance(n, str) and n.strip()]

    if scene.get("good_tracks"):
        names = scene.get("good_tracks_names", [])
        return [n for n in names if isinstance(n, str) and n.strip()]

    return []


def _resolve_calibrate_track_names(scene: bpy.types.Scene) -> List[str]:
    """Lädt calibrate_tracks_names, falls vorhanden."""
    if not scene.get("calibrate_tracks"):
        return []
    names = scene.get("calibrate_tracks_names", [])
    return [n for n in names if isinstance(n, str) and n.strip()]


# ------------------------------------------------------------
# Haupt-Helper (Forward-Motion-Check für Backward-Tracking)
# ------------------------------------------------------------
def validate_calibrate_tracks_backward_window(context: bpy.types.Context) -> None:
    scene = context.scene
    clip = getattr(context.space_data, "clip", None)
    if clip is None:
        print("[ValidateBackwardMotion] Kein Clip gefunden.")
        return

    # --------------------------------------------------------
    # Track-Listen sauber aus Scene Properties laden
    # --------------------------------------------------------
    ref_list = _resolve_reference_track_names(scene)
    if not ref_list:
        print("[ValidateBackwardMotion] Keine good/best Tracks → Abbruch.")
        return

    calibrate_list = _resolve_calibrate_track_names(scene)
    if not calibrate_list:
        print("[ValidateBackwardMotion] Keine calibrate_tracks → Abbruch.")
        return

    # --------------------------------------------------------
    # Δ-Vektoren aus Referenz (Best/Good) berechnen für Zukunftsdaten
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
        print("[ValidateBackwardMotion] Keine gültigen Bewegungsvektoren.")
        return

    avg_dx = sum(dx_values) / len(dx_values)
    avg_dy = sum(dy_values) / len(dy_values)

    print(f"[Reference Δ BW] avg_dx={avg_dx:.6f}, avg_dy={avg_dy:.6f}")

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

        print(f"[Check BW {name}] Δx={dx:.6f} Δy={dy:.6f} | DevX={dev_x:.6f}, DevY={dev_y:.6f}")

        if dev_x > max_dev or dev_y > max_dev:
            marker = track.markers.find_frame(current_frame, exact=True)
            if marker:
                marker.mute = True
                print(f" → [MUTED BW @ {current_frame}] Track {name} (abweichend!)")


# ------------------------------------------------------------
# Aufruf-Beispiel in einem Operator:
# validate_calibrate_tracks_backward_window(context)
# ------------------------------------------------------------
