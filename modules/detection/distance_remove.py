"""Utilities for removing tracks based on proximity."""

import bpy
from mathutils import Vector


def distance_remove(tracks, good_marker, margin):
    """Remove tracks within a margin of a given marker."""
    good_pos = Vector(good_marker)
    for track in list(tracks):
        try:
            pos = track.markers[0].co
        except (AttributeError, IndexError):
            continue
        if (Vector(pos) - good_pos).length < margin:
            safe_track = tracks.get(track.name) if hasattr(tracks, "get") else track
            if safe_track:
                tracks.remove(safe_track)

