import bpy

from .prefix_track import PREFIX_TRACK
from .utils import clean_pending_tracks, PENDING_RENAME


def _get_undertracked_markers(clip, min_frames=10):
    undertracked = []
    clean_pending_tracks(clip)
    for track in clip.tracking.tracks:
        if not (track.name.startswith(PREFIX_TRACK) or track in PENDING_RENAME):
            continue
        tracked_frames = [
            m for m in track.markers
            if not m.mute and m.co.length_squared != 0.0
        ]
        if len(tracked_frames) < min_frames:
            undertracked.append((track.name, len(tracked_frames)))
    return undertracked


def _select_tracks_by_names(clip, name_list):
    for track in clip.tracking.tracks:
        track.select = track.name in name_list


def select_short_tracks(clip, min_length: int):
    """Select TRACK_ markers shorter than ``min_length`` and return count."""
    undertracked = _get_undertracked_markers(clip, min_frames=min_length)
    for t in clip.tracking.tracks:
        t.select = False
    if not undertracked:
        return 0
    names = [name for name, _ in undertracked]
    _select_tracks_by_names(clip, names)
    return len(names)
