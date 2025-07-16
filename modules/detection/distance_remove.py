"""Utilities for removing tracks based on proximity."""

from mathutils import Vector
from ..util.tracking_utils import safe_remove_track


def distance_remove(tracks, good_marker, margin, logger=None):
    """Remove tracks within ``margin`` distance of ``good_marker``."""
    good_pos = Vector(good_marker)
    for track in list(tracks):
        if not getattr(track, "name", "").startswith("NEW_"):
            continue
        try:
            pos = track.markers[0].co
        except (AttributeError, IndexError):
            continue
        dist = (Vector(pos) - good_pos).length
        if dist < margin:
            safe_track = tracks.get(track.name) if hasattr(tracks, "get") else track
            if safe_track:
                clip = getattr(tracks, "id_data", None)
                if logger:
                    logger.info(f"Entferne {track.name} mit Distanz {dist:.3f}")
                safe_remove_track(clip, safe_track, logger=logger)

