# Helper/marker_positions_helper_bidir.py
import bpy
from typing import List, Tuple


def get_positions_bidir(
    track: "bpy.types.MovieTrackingTrack",
    current_frame: int,
    max_frames: int = 5,
) -> list[tuple[int, any]]:
    """
    Liefert Markerpositionen um den aktuellen Frame herum (bidirektional).

    Idee:
    - max_frames kommt von außen (z.B. scene.kaiserlich_frames_per_track)
    - Wir interpretieren max_frames als "Fenstergröße" und halbieren:
        half = max(1, int(max_frames // 2))
    - Dann betrachten wir:
        [current_frame - half, ..., current_frame, ..., current_frame + half]
      → aktueller Frame liegt immer im Fenster, wenn dort ein Marker existiert.

    Rückgabe:
        Liste von (frame, marker.co.copy()) für alle Frames im Fenster,
        bei denen der Track einen aktiven Marker hat.
    """

    markers = track.markers
    positions: list[tuple[int, any]] = []

    # Sicherstellen, dass wir mit einer sinnvollen Fenstergröße arbeiten
    try:
        max_frames_int = int(max_frames)
    except Exception:
        max_frames_int = 5

    if max_frames_int < 2:
        max_frames_int = 2

    # Hälfte vor / Hälfte nach dem Playhead
    half = max(1, max_frames_int // 2)

    start_frame = current_frame - half
    end_frame = current_frame + half

    # Bidirektionales Fenster: vom ersten bis zum letzten Frame im Bereich
    for frame in range(start_frame, end_frame + 1):
        try:
            f_int = int(round(frame))
        except Exception:
            continue

        marker = None
        try:
            # exact=True, damit wir nur echte Marker-Frames bekommen
            marker = markers.find_frame(f_int, exact=True)
        except Exception:
            continue

        # Nur berücksichtigen, wenn Marker existiert und aktiv ist
        if not marker:
            continue
        if getattr(marker, "mute", False):
            continue
        if getattr(track, "mute", False):
            continue

        positions.append((f_int, marker.co.copy()))

    return positions
