"""Iterative feature detection until the marker count is within range.

This helper combines detection from :mod:`detect` with the counting logic of
:mod:`count_new_markers`. It starts with threshold 1.0 and recomputes
margin and distance based on the last result. When the count finally
matches the expected range, the markers are renamed with the prefix
``TRACK_``.
"""

import bpy

from margin_a_distanz import compute_margin_distance
from margin_distance_adapt import ensure_margin_distance
from adjust_marker_count_plus import adjust_marker_count_plus
from count_new_markers import count_new_markers
from rename_new import rename_tracks as rename_new_tracks
from rename_track import rename_tracks as rename_track_tracks


def detect_until_count_matches(context):
    """Detect markers repeatedly until the count is within the desired range."""

    scene = context.scene
    space = getattr(context, "space_data", None)
    clip = getattr(space, "clip", None)
    if clip is None:
        clip = getattr(scene, "clip", None)
    if not clip:
        print("Kein Clip gefunden")
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
        rename_new_tracks(list(clip.tracking.tracks)[base_idx:])
        return count_new_markers(context, clip)

    new_count = detect_step()
    min_expected = scene.marker_count_plus_min
    max_expected = scene.marker_count_plus_max

    while not (min_expected <= new_count <= max_expected) and threshold > 0.0001:
        prev_count = new_count
        for track in list(clip.tracking.tracks)[base_idx:]:
            track.select = True
        bpy.ops.clip.delete_track()

        adjust_marker_count_plus(scene, prev_count)
        min_plus = max(1, scene.min_marker_count_plus)
        threshold = max(threshold * ((prev_count + 0.1) / min_plus), 0.0001)
        margin, distance, _ = ensure_margin_distance(clip, threshold)
        new_count = detect_step()
        min_expected = scene.marker_count_plus_min
        max_expected = scene.marker_count_plus_max

    rename_track_tracks(list(clip.tracking.tracks)[base_idx:])
    return new_count
