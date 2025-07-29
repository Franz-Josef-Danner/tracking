import bpy

from .track_selection_utils import get_undertracked_markers, select_tracks_by_names


def select_short_tracks(clip, min_length: int):
    """Select ``TRACK_`` markers shorter than ``min_length`` and return count.

    Used by :class:`~operators.tracking.cleanup.CLIP_OT_select_short_tracks`.
    """
    undertracked = get_undertracked_markers(clip, min_frames=min_length)
    for t in clip.tracking.tracks:
        t.select = False
    if not undertracked:
        return 0
    names = [name for name, _ in undertracked]
    select_tracks_by_names(clip, names)
    return len(names)
