from .process_marker_path import get_track_segments

def _iter_tracks(x):
    try:
        return list(x)
    except TypeError:
        return [x]

def _last_keyed_or_last_marker_frame(track):
    keyed = [m.frame for m in track.markers if getattr(m, "is_keyed", False)]
    return max(keyed) if keyed else (max((m.frame for m in track.markers), default=None))

def _delete_boundary_keys(track):
    """
    Löscht harte Keyframes exakt auf Segment-Start und Segment-Ende.
    Wichtig: vor dem restlichen Cleanup ausführen und danach Segmente neu bilden.
    """
    segments = get_track_segments(track)
    for start, end in segments:
        for f in (start, end):
            m = track.markers.find_frame(f)
            if m and getattr(m, "is_keyed", False):
                track.markers.delete_frame(f)

def mute_invalid_segments(track_or_tracks, scene_end, action="mute"):
    for track in _iter_tracks(track_or_tracks):
        if not hasattr(track, "markers") or not track.markers:
            continue

        # 1) Grenz-Keyframes immer entfernen
        _delete_boundary_keys(track)

        # 2) Segmente nach dem Löschen neu berechnen
        segments = get_track_segments(track)
        if not segments:
            continue

        # gültig = nur Segmente mit >=2 Frames
        valid_frames = set()
        for start, end in segments:
            if end - start + 1 >= 2:
                valid_frames.update(range(start, end + 1))

        # harte Obergrenze für geschätzte Marker
        last_keyed = _last_keyed_or_last_marker_frame(track)

        def invalid(f):
            if f not in valid_frames:
                return True
            if last_keyed is not None and f > last_keyed:
                return True
            return False

        if action == "delete":
            to_delete = sorted({m.frame for m in track.markers if invalid(m.frame)})
            for f in to_delete:
                track.markers.delete_frame(f)
        else:
            for m in track.markers:
                if invalid(m.frame):
                    m.mute = True
