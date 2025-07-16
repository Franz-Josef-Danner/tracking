"""Locate frames with few tracking markers."""

def find_frame_with_few_tracking_markers(clip, min_markers):
    """Return the first frame with fewer markers than `min_markers`."""
    for frame in range(
        clip.frame_start,
        clip.frame_start + clip.frame_duration,
    ):
        count = 0
        for track in clip.tracking.tracks:
            if any(m.frame == frame for m in track.markers):
                count += 1
        if count < min_markers:
            return frame
    return None

