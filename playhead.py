"""Utilities for adjusting the playhead position."""

import bpy
from collections import Counter
import logging

from few_marker_frame import (
    find_frame_with_few_tracking_markers,
)


def get_tracking_marker_counts():
    """Return a Counter of marker counts for each frame across all clips."""
    marker_counts = Counter()
    for clip in bpy.data.movieclips:
        for track in clip.tracking.tracks:
            for marker in track.markers:
                marker_counts[marker.frame] += 1
    return marker_counts


logger = logging.getLogger(__name__)


def set_playhead_to_low_marker_frame(minimum_count):
    """Move the playhead to the first frame with too few markers and log info."""
    counts = get_tracking_marker_counts()
    frame = find_frame_with_few_tracking_markers(counts, minimum_count)
    if frame is not None:
        scene = bpy.context.scene
        scene.frame_current = frame

        clip = getattr(bpy.context.space_data, "clip", None)
        settings = clip.tracking.settings if clip else None

        pattern_size = settings.default_pattern_size if settings else "n/a"
        threshold = getattr(scene, "error_threshold", "n/a")

        logger.info(
            "Playhead auf Frame %s gesetzt. threshold=%s pattern_size=%s min_marker_count=%s",
            frame,
            threshold,
            pattern_size,
            minimum_count,
        )
    else:
        logger.info("Kein passender Frame gefunden.")
