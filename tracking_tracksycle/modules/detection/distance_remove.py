"""Utilities for removing tracks based on proximity."""

import bpy


def distance_remove(tracks, good_marker, margin):
    """Remove tracks within a margin of a given marker."""
    for track in tracks:
        if (track.marker_pos - good_marker).length < margin:
            tracks.remove(track)

