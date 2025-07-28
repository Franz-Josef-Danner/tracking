import bpy


def find_next_low_marker_frame(scene, clip, marker_threshold: int):
    """Return ``(frame, count)`` for the first frame below ``marker_threshold``."""
    for frame in range(scene.frame_start, scene.frame_end + 1):
        count = 0
        for track in clip.tracking.tracks:
            marker = track.markers.find_frame(frame)
            if marker and not marker.mute and marker.co.length_squared != 0.0:
                count += 1
        if count < marker_threshold:
            return frame, count
    return None, 0
