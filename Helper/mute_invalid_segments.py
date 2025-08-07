# Helper/mute_invalid_segments.py
from .process_marker_path import get_track_segments

__all__ = ["mute_invalid_segments", "remove_segment_boundary_keys"]

def _iter_tracks(x):
    try:
        return list(x)
    except TypeError:
        return [x]

def remove_segment_boundary_keys(track_or_tracks, only_if_keyed=True, also_track_bounds=True):
    """
    Löscht Keyframes genau an Segment-Grenzen (start/end).
    Optional auch am globalen Track-Start/-Ende.
    """
    for track in _iter_tracks(track_or_tracks):
        markers = getattr(track, "markers", None)
        if not markers:
            continue

        segs = get_track_segments(track)
        if not segs:
            continue

        frames_to_check = set()
        for s, e in segs:
            frames_to_check.add(s)
            frames_to_check.add(e)

        if also_track_bounds:
            all_frames = [m.frame for m in markers]
            if all_frames:
                frames_to_check.add(min(all_frames))
                frames_to_check.add(max(all_frames))

        for f in sorted(frames_to_check):
            m = markers.find_frame(f)
            if not m:
                continue
            if only_if_keyed and not getattr(m, "is_keyed", False):
                continue
            markers.delete_frame(f)

def mute_invalid_segments(track_or_tracks, scene_end=None, action="mute"):
    """
    Rechnet gültige Segmente (>=2 Frames) neu aus und
    mute/t delete-t alles außerhalb + nach letztem Keyframe.
    """
    for track in _iter_tracks(track_or_tracks):
        markers = getattr(track, "markers", None)
        if not markers:
            continue

        # HARTE Grenze zuerst: Keys an Segment/Track-Grenzen weg
        remove_segment_boundary_keys(track, only_if_keyed=True, also_track_bounds=True)

        segs = get_track_segments(track)
        if not segs:
            continue

        valid_frames = set()
        for s, e in segs:
            if e - s + 1 >= 2:
                valid_frames.update(range(s, e + 1))

        keyed = [m.frame for m in markers if getattr(m, "is_keyed", False)]
        last_keyed = max(keyed) if keyed else None

        def is_invalid(m):
            f = m.frame
            if f not in valid_frames:
                return True
            if last_keyed is not None and f > last_keyed:
                return True
            return False

        if action == "delete":
            to_delete = [m.frame for m in list(markers) if is_invalid(m)]
            for f in sorted(set(to_delete)):
                markers.delete_frame(f)
        else:
            for m in markers:
                if is_invalid(m):
                    m.mute = True
