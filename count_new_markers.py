"""Helpers for counting and validating NEW_ markers."""

import bpy

from delet import delete_close_new_markers
from adjust_marker_count_plus import adjust_marker_count_plus
from margin_distance_adapt import ensure_margin_distance


def count_new_markers(clip, prefix="NEW_"):
    """Return the number of tracks starting with ``prefix``."""
    return sum(1 for t in clip.tracking.tracks if t.name.startswith(prefix))


def check_marker_range(context, clip, prefix="NEW_"):
    """Validate the count of NEW_ markers and rerun detection if needed."""

    scene = context.scene
    new_count = count_new_markers(clip, prefix)
    min_count = getattr(scene, "marker_count_plus_min", 0)
    max_count = getattr(scene, "marker_count_plus_max", 0)

    if min_count <= new_count <= max_count:
        return new_count

    delete_close_new_markers(context)
    adjust_marker_count_plus(scene, new_count)
    ensure_margin_distance(clip)
    bpy.ops.clip.detect_features_custom()
    return new_count
