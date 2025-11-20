# Helper.validate_motion_forward_helper.py
from __future__ import annotations
import bpy
from typing import List
from .logging_helper import tracker_log

_LOG_SCOPE = "FORWARD_VAL"


# ============================================================
# Hilfsfunktion: Marker-Positionen rückwärts (für FW-Vergleich)
# ============================================================
def _get_positions_backward(track: bpy.types.MovieTrackingTrack,
                            current_frame: int,
                            max_frames: int = 4) -> List[tuple[int, tuple[float, float]]]:

    positions = []
    markers = track.markers
    start = current_frame - max_frames

    tracker_log("VALIDATE", _LOG_SCOPE, f"get_positions track={track.name} from={current_frame} to={start}")

    for frame in range(current_frame, start - 1, -1):
        marker = markers.find_frame(frame, exact=True)
        if not marker:
            tracker_log("VALIDATE", _LOG_SCOPE, f"frame {frame} missing_marker")
            continue
        if not marker.co:
            tracker_log("VALIDATE", _LOG_SCOPE, f"frame {frame} no_coords")
            continue

        co = marker.co.copy()
        positions.append((frame, co))
        tracker_log("VALIDATE", _LOG_SCOPE, f"frame {frame} pos=({co[0]:.6f},{co[1]:.6f})")

    return positions


# ============================================================
# Track-Lister (robust against UUID lists / empty placeholders)
# ============================================================
def _resolve_reference_track_names(scene: bpy.types.Scene) -> List[str]:
    # Priorität: BEST
    names = scene.get("best_tracks_names", [])
    if isinstance(names, list) and names:
        tracker_log("VALIDATE", _LOG_SCOPE, f"resolve_ref best_tracks={len(names)}")
        return [n for n in names if isinstance(n, str) and n.strip()]

    # Fallback: GOOD
    names = scene.get("good_tracks_names", [])
    if isinstance(names, list) and names:
        tracker_log("VALIDATE", _LOG_SCOPE, f"resolve_ref good_tracks={len(names)}")
        return [n for n in names if isinstance(n, str) and n.strip()]
    tracker_log("VALIDATE", _LOG_SCOPE, "resolve_ref none_found")
    return []


def _resolve_calibrate_track_names(scene: bpy.types.Scene) -> List[str]:
    # Ausschließlich *_names verwenden
    names = scene.get("calibrate_tracks", [])
    if isinstance(names, list) and names:
        tracker_log("VALIDATE", _LOG_SCOPE, f"resolve_cal calibrate_tracks={len(names)}")
        return [n for n in names if isinstance(n, str) and n.strip()]
    tracker_log("VALIDATE", _LOG_SCOPE, "resolve_cal none_found")
    return []


# ============================================================
# Hauptroutine (Forward-Motion Validierung / BW Δ Vergleich)
# ============================================================
def validate_calibrate_tracks_against_motion(context: bpy.types.Context) -> None:
    scene = context.scene
    clip = getattr(context.space_data, "clip", None)

    tracker_log("VALIDATE", _LOG_SCOPE, "start")

    if clip is None:
        tracker_log("VALIDATE", _LOG_SCOPE, "abort:no_clip")
        return

    # ---- Namen laden ----
    ref_list = _resolve_reference_track_names(scene)
    if not ref_list:
        tracker_log("VALIDATE", _LOG_SCOPE, "abort:no_ref_tracks")
        return

    calibrate_list = _resolve_calibrate_track_names(scene)
    if not calibrate_list:
        tracker_log("VALIDATE", _LOG_SCOPE, "abort:no_calibrate_tracks")
        return

    current_frame = scene.frame_current
    tracker_log("VALIDATE", _LOG_SCOPE, f"frame={current_frame}")

    # ---- Referenz-Vektoren sammeln ----
    dx_values, dy_values = [], []

    tracker_log("VALIDATE", _LOG_SCOPE, "ref_calc_start")
    for name in ref_list:
        track = clip.tracking.tracks.get(name)
        if not track:
            tracker_log("VALIDATE", _LOG_SCOPE, f"ref {name} missing")
            continue

        pos = _get_positions_backward(track, current_frame, 4)
        if len(pos) < 2:
            tracker_log("VALIDATE", _LOG_SCOPE, f"ref {name} too_few_markers={len(pos)}")
            continue

        (_, (x1, y1)), (_, (x2, y2)) = pos[0], pos[1]
        dx = x1 - x2
        dy = y1 - y2

        dx_values.append(dx)
        dy_values.append(dy)

        tracker_log("VALIDATE", _LOG_SCOPE, f"ref {name} dx={dx:.6f} dy={dy:.6f}")

    if not dx_values or not dy_values:
        tracker_log("VALIDATE", _LOG_SCOPE, "abort:no_vectors")
        return

    avg_dx = sum(dx_values) / len(dx_values)
    avg_dy = sum(dy_values) / len(dy_values)
    tracker_log("VALIDATE", _LOG_SCOPE, f"ref_avg dx={avg_dx:.6f} dy={avg_dy:.6f}")

    # ---- Threshold bestimmen ----
    max_dev = getattr(scene, "max_error_value", 5.0) / 500.0
    tracker_log("VALIDATE", _LOG_SCOPE, f"threshold max_dev={max_dev:.6f}")

    # ---- Calibrate-Tracks prüfen ----
    tracker_log("VALIDATE", _LOG_SCOPE, "calibrate_check_start")
    for name in calibrate_list:
        track = clip.tracking.tracks.get(name)
        if not track:
            tracker_log("VALIDATE", _LOG_SCOPE, f"cal {name} missing")
            continue

        pos = _get_positions_backward(track, current_frame, 4)
        if len(pos) < 2:
            tracker_log("VALIDATE", _LOG_SCOPE, f"cal {name} too_few_markers={len(pos)}")
            continue

        (_, (x1, y1)), (_, (x2, y2)) = pos[0], pos[1]
        dx = x1 - x2
        dy = y1 - y2

        dev_x = abs(dx - avg_dx)
        dev_y = abs(dy - avg_dy)

        tracker_log("VALIDATE", _LOG_SCOPE, f"cal {name} dx={dx:.6f} dy={dy:.6f} devx={dev_x:.6f} devy={dev_y:.6f}")

        if dev_x > max_dev or dev_y > max_dev:
            marker = track.markers.find_frame(current_frame, exact=True)
            if marker:
                marker.mute = True
                tracker_log("VALIDATE", _LOG_SCOPE, f"mute track={name} frame={current_frame}")
            else:
                tracker_log("VALIDATE", _LOG_SCOPE, f"mute_failed track={name} frame={current_frame} no_marker")

    tracker_log("VALIDATE", _LOG_SCOPE, "end")
