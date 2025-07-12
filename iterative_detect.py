"""Iterative feature detection until the marker count is within range.

This helper combines detection from :mod:`detect` with the counting logic of
:mod:`count_new_markers`. It starts with threshold 1.0 and recomputes
margin and distance based on the last result. When the count finally
matches the expected range, the markers are renamed with the prefix
``TRACK_``.
"""

import bpy
import logging

from margin_utils import compute_margin_distance, ensure_margin_distance
from count_new_markers import count_new_markers
from rename_new import rename_tracks as rename_new_tracks
from utils import get_active_clip

logger = logging.getLogger(__name__)


def detect_until_count_matches(context):
    """Detect markers repeatedly until the count is within the desired range."""

    scene = context.scene
    clip = get_active_clip(context)
    if not clip:
        logger.info("Kein Clip gefunden")
        return 0

    compute_margin_distance()

    base_idx = len(clip.tracking.tracks)
    threshold = 1.0
    margin, distance, _ = ensure_margin_distance(clip, threshold)

    def detect_step():
        bpy.ops.clip.detect_features(
            threshold=threshold,
            margin=margin,
            min_distance=distance,
            placement='FRAME',
        )
        new_tracks = list(clip.tracking.tracks)[base_idx:]
        rename_new_tracks(new_tracks)
        logger.info(
            "Detect step: %s %s %s",
            f"threshold={threshold:.4f}",
            f"→ erzeugt {len(new_tracks)} Marker",
            f"{[t.name for t in new_tracks]}",
        )
        new_count = count_new_markers(context, clip)
        logger.info(f"Gespeicherte NEW_-Marker: {scene.new_marker_count}")
        return new_count

    new_count = detect_step()
    min_expected = scene.marker_count_plus_min
    max_expected = scene.marker_count_plus_max

    while not (min_expected <= new_count <= max_expected) and threshold > 0.0001:
        prev_count = new_count
        delete_tracks = list(clip.tracking.tracks)[base_idx:]
        for track in delete_tracks:
            track.select = True
        logger.info("Lösche Marker: %s", [t.name for t in delete_tracks])
        bpy.ops.clip.delete_track()

        min_plus = max(1, scene.min_marker_count_plus)
        threshold = max(threshold * ((prev_count + 0.1) / min_plus), 0.0001)
        margin, distance, _ = ensure_margin_distance(clip, threshold)
        new_count = detect_step()
        min_expected = scene.marker_count_plus_min
        max_expected = scene.marker_count_plus_max

    final_tracks = list(clip.tracking.tracks)[base_idx:]
    rename_new_tracks(final_tracks, prefix="TRACK_")
    logger.info("Finale TRACK_ Marker: %s", [t.name for t in final_tracks])
    return new_count
