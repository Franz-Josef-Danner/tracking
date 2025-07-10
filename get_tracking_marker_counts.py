"""Utility: count tracking markers per frame."""

from collections import Counter
import bpy


def get_tracking_marker_counts(clip=None):
    """Return a mapping of frame numbers to the number of markers."""

    if clip is None:
        clip = bpy.context.space_data.clip
        if not clip:
            return Counter()

    marker_counts = Counter()
    for track in clip.tracking.tracks:
        for marker in track.markers:
            frame = marker.frame
            marker_counts[frame] += 1
    return marker_counts

