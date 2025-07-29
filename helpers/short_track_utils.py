import bpy

from .marker_helpers import get_undertracked_markers, select_tracks_by_names


def _select_tracks_by_names(clip, name_list):
    """Select tracks from ``name_list`` in the given clip."""
    select_tracks_by_names(clip, name_list)


def select_short_tracks(clip, min_length: int):
    """Select ``TRACK_`` markers shorter than ``min_length`` and return count."""
    undertracked = get_undertracked_markers(clip, min_frames=min_length)
    for t in clip.tracking.tracks:
        t.select = False
    if not undertracked:
        return 0
    names = [name for name, _ in undertracked]
    _select_tracks_by_names(clip, names)
    return len(names)
