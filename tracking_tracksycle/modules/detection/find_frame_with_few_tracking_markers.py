"""Locate frames with few tracking markers."""

import bpy


def find_frame_with_few_tracking_markers(clip, min_markers):
    """Return the first frame with fewer markers than `min_markers`."""
    for frame in range(clip.frame_start, clip.frame_end + 1):
        markers = [m for m in clip.tracking.tracks if frame in [mk.frame for mk in m.markers]]
        if len(markers) < min_markers:
            return frame
    return None

