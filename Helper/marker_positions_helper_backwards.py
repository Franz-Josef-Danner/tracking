# Helper/marker_positions_helper_backwards.py
import bpy


def get_positions_backward(track: 'bpy.types.MovieTrackingTrack', current_frame: int, max_frames: int = 5):

    markers = track.markers
    positions: list[tuple[int, any]] = []

    start_frame = current_frame - (max_frames + 1)

    for frame in range(start_frame, current_frame + 1):

        try:
            f_int = int(round(frame))
        except Exception:
            continue

        f_int = max(start_frame, min(f_int, current_frame))

        marker = None
        try:
            marker = markers.find_frame(f_int)
        except Exception as e:
            continue

        if marker:
            positions.append((f_int, marker.co.copy()))
    return positions
