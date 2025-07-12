"""Helpers for counting and validating NEW_ markers."""

import bpy

from delete_helpers import delete_close_new_markers, delete_new_markers
from adjust_marker_count_plus import adjust_marker_count_plus
from margin_utils import ensure_margin_distance
from rename_new import rename_tracks


def count_new_markers(context, clip, prefix="NEW_"):
    """Return and store the number of tracks starting with ``prefix``."""

    new_count = sum(1 for t in clip.tracking.tracks if t.name.startswith(prefix))
    context.scene.new_marker_count = new_count
    return new_count


def check_marker_range(context, clip, prefix="NEW_"):
    """Validate the count of NEW_ markers and rerun detection if needed."""

    scene = context.scene
    new_count = count_new_markers(context, clip, prefix)
    min_count = getattr(scene, "marker_count_plus_min", 0)
    max_count = getattr(scene, "marker_count_plus_max", 0)

    if min_count <= new_count <= max_count:
        print(f"NEW_-Marker {new_count} liegt im Bereich {min_count}-{max_count}")
        return new_count

    deleted = delete_new_markers(context)
    if deleted:
        print(f"🗑️ Gelöscht: {deleted} NEW_-Marker")
    else:
        delete_close_new_markers(context)
    adjust_marker_count_plus(scene, new_count)
    ensure_margin_distance(clip)
    print(
        f"NEW_-Marker {new_count} außerhalb des Bereichs {min_count}-{max_count}"
        " → erneute Erkennung"
    )
    start_idx = len(clip.tracking.tracks)
    bpy.ops.clip.detect_features_custom()
    rename_tracks(list(clip.tracking.tracks)[start_idx:])
    new_count = count_new_markers(context, clip, prefix)
    return new_count
