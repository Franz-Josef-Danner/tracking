# Helper/marker_positions_helper_backwards.py
import bpy
from .logging_helper import tracker_log


def get_positions_backward(track: 'bpy.types.MovieTrackingTrack', current_frame: int, max_frames: int = 5):
    tracker_log("POSITIONS", "BACKWARD", f"start track={getattr(track,'name',None)} frame={current_frame} span={max_frames}")

    markers = track.markers
    positions: list[tuple[int, any]] = []

    end_frame = current_frame + (max_frames - 1)

    for frame in range(current_frame, end_frame + 1):

        try:
            f_int = int(round(frame))
        except Exception:
            continue

        f_int = min(end_frame, max(f_int, current_frame))

        marker = None
        try:
            marker = markers.find_frame(f_int)
        except Exception as e:
            continue

        if marker:
            positions.append((f_int, marker.co.copy()))
    if positions:
        tracker_log("POSITIONS", "BACKWARD", f"done count={len(positions)} first={positions[0][0]} last={positions[-1][0]}")
    else:
        tracker_log("POSITIONS", "BACKWARD", "done count=0")
    return positions
