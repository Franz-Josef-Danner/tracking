import bpy
from .prefix_track import PREFIX_TRACK
from .utils import PENDING_RENAME, clean_pending_tracks


def has_active_marker(tracks, frame):
    for t in tracks:
        m = t.markers.find_frame(frame)
        if m and not m.mute and m.co.length_squared != 0.0:
            return True
    return False


def get_undertracked_markers(clip, min_frames=10):
    undertracked = []
    clean_pending_tracks(clip)
    for track in clip.tracking.tracks:
        if not (track.name.startswith(PREFIX_TRACK) or track in PENDING_RENAME):
            continue
        tracked_frames = [
            m
            for m in track.markers
            if not m.mute and m.co.length_squared != 0.0
        ]
        if len(tracked_frames) < min_frames:
            undertracked.append((track.name, len(tracked_frames)))
    return undertracked


def select_tracks_by_names(clip, name_list):
    for track in clip.tracking.tracks:
        track.select = track.name in name_list


def select_tracks_by_prefix(clip, prefix):
    """Select all tracks whose names start with the given prefix."""
    for track in clip.tracking.tracks:
        track.select = track.name.startswith(prefix)


def ensure_valid_selection(clip, frame):
    """Validate selected tracks for the given frame."""
    valid = False
    for track in clip.tracking.tracks:
        if track.select:
            marker = track.markers.find_frame(frame, exact=True)
            if marker is None or marker.mute:
                track.select = False
            else:
                valid = True
    return valid


def cleanup_all_tracks(clip):
    """Remove all tracks from the clip."""
    for t in clip.tracking.tracks:
        t.select = True
    from .delete_tracks import delete_selected_tracks

    delete_selected_tracks()
