from .process_marker_path import get_track_segments

def _iter_tracks(x):
    try:
        return list(x)
    except TypeError:
        return [x]

def remove_segment_boundary_keys(track_or_tracks, only_if_keyed=True):
    """
    Löscht NUR die Marker direkt auf Segment-Start und -Ende.
    Kein forward/backward-Sweep.
    """
    for track in _iter_tracks(track_or_tracks):
        if not getattr(track, "markers", None):
            continue
        segments = get_track_segments(track)
        for start, end in segments:
            for f in (start, end):
                m = track.markers.find_frame(f)
                if not m:
                    continue
                if (not only_if_keyed) or getattr(m, "is_keyed", False):
                    track.markers.delete_frame(f)

def prune_outside_segments(track_or_tracks, action="mute"):
    """
    Hält nur zusammenhängende Segmente >=2 Frames.
    Alles andere (Einzelmarker, Lückenreste, 'estimated' nach dem Ende) wird
    je nach action gemutet oder gelöscht.
    """
    for track in _iter_tracks(track_or_tracks):
        if not getattr(track, "markers", None):
            continue

        segments = get_track_segments(track)
        if not segments:
            continue

        valid_frames = set()
        for start, end in segments:
            if end - start + 1 >= 2:
                valid_frames.update(range(start, end + 1))

        if action == "delete":
            # vorsicht: in Liste casten, damit wir während der Iteration löschen können
            for m in list(track.markers):
                if m.frame not in valid_frames:
                    track.markers.delete_frame(m.frame)
        else:
            for m in track.markers:
                if m.frame not in valid_frames:
                    m.mute = True
