"""Utilities for adjusting the playhead position."""

import bpy
from collections import Counter
import logging




def get_tracking_marker_counts():
    """Return a Counter of marker counts for each frame across all clips."""
    marker_counts = Counter()
    for clip in bpy.data.movieclips:
        for track in clip.tracking.tracks:
            for marker in track.markers:
                marker_counts[marker.frame] += 1
    return marker_counts


logger = logging.getLogger(__name__)
