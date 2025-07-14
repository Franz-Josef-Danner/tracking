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
            idx = tracks.find(track.name)
            if idx != -1:
                tracks.remove(idx)

