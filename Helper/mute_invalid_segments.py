from .process_marker_path import get_track_segments

__all__ = ["mute_invalid_segments", "remove_segment_boundary_keys"]

def _iter_tracks(x):
    try:
        return list(x)
    except TypeError:
        return [x]

def remove_segment_boundary_keys(track_or_tracks, only_if_keyed=True, also_track_bounds=True):
    """
    Löscht Keyframes genau an Segmentgrenzen und optional am Track-Start/-Ende.
    Entfernt nur echte Keys, wenn only_if_keyed=True.
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
            # nur löschen, wenn keyed verlangt oder egal
            if only_if_keyed and not getattr(m, "is_keyed", False):
                continue
            markers.delete_frame(f)

def mute_invalid_segments(track_or_tracks, scene_end=None, action="mute"):
    """
    Gültig sind nur Segmente mit Länge >=2. Alles außerhalb wird gemutet/gelöscht.
    Außerdem wird nach dem letzten Keyframe (falls vorhanden) ebenfalls gemutet/gelöscht.
    """
    for track in _iter_tracks(track_or_tracks):
        markers = getattr(track, "markers", None)
        if not markers:
            continue

        # Safety: an Segment- & Trackgrenzen KEINE Keys stehen lassen
        remove_segment_boundary_keys(track, only_if_keyed=True, also_track_bounds=True)

        segs = get_track_segments(track)
        if not segs:
            continue

        valid_frames = set()
        for s, e in segs:
            if e - s + 1 >= 2:
                valid_frames.update(range(s, e + 1))

        keyed_frames = [m.frame for m in markers if getattr(m, "is_keyed", False)]
        last_keyed = max(keyed_frames) if keyed_frames else None

        def is_invalid_marker(m):
            f = m.frame
            if f not in valid_frames:
                return True
            if last_keyed is not None and f > last_keyed:
                return True
            return False

        if action == "delete":
            to_delete = [m.frame for m in list(markers) if is_invalid_marker(m)]
            for f in sorted(set(to_delete)):
                markers.delete_frame(f)
        else:
            for m in markers:
                if is_invalid_marker(m):
                    m.mute = True
