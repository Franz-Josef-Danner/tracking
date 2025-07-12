"""Utilities to find frames with few tracking markers and move the playhead."""

from collections import Counter
import logging
import types
try:
    import bpy
except ModuleNotFoundError:  # pragma: no cover - only used during testing
    import sys
    bpy = types.SimpleNamespace(
        data=types.SimpleNamespace(movieclips=[]),
        context=types.SimpleNamespace(
            scene=types.SimpleNamespace(
                frame_start=1,
                frame_end=1,
                frame_current=1,
                min_marker_count=1,
            )
        ),
    )
    sys.modules.setdefault('bpy', bpy)

logger = logging.getLogger(__name__)


def find_frame_with_few_tracking_markers(marker_counts, minimum_count):
    """Return the first frame with fewer markers than ``minimum_count``."""
    start = bpy.context.scene.frame_start
    end = bpy.context.scene.frame_end
    for frame in range(start, end + 1):
        if marker_counts.get(frame, 0) < minimum_count:
            return frame
    return None


def get_tracking_marker_counts():
    """Return a Counter of marker counts for each frame across all clips."""
    marker_counts = Counter()
    for clip in bpy.data.movieclips:
        for track in clip.tracking.tracks:
            for marker in track.markers:
                marker_counts[marker.frame] += 1
    return marker_counts


def set_playhead_to_low_marker_frame(minimum_count=None):
    """Move the playhead to the first frame with too few markers."""
    if minimum_count is None:
        minimum_count = bpy.context.scene.min_marker_count
    counts = get_tracking_marker_counts()
    frame = find_frame_with_few_tracking_markers(counts, minimum_count)
    if frame is not None:
        bpy.context.scene.frame_current = frame
        logger.info("Playhead auf Frame %s gesetzt", frame)
    else:
        logger.info("Kein passender Frame gefunden")
    return frame
