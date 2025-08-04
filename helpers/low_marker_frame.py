import bpy


def low_marker_frame(
    scene: bpy.types.Scene, clip: bpy.types.MovieClip, threshold: int
) -> list[tuple[int, int]]:
    """Return frames with too few unmuted markers.

    Each tuple in the returned list consists of the frame number and the
    detected marker count for that frame.
    """
    if clip is None:
        return []

    low_marker_frames: list[tuple[int, int]] = []

    for frame in range(scene.frame_start, scene.frame_end + 1):
        count = 0
        for track in clip.tracking.objects.active.tracks:
            marker = track.markers.find_frame(frame, exact=True)
            if marker and not marker.mute:
                count += 1

        if count < threshold:
            low_marker_frames.append((frame, count))

    return low_marker_frames
