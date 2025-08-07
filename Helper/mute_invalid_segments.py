from .process_marker_path import get_track_segments

def _iter_tracks(x):
    try:
        return list(x)
    except TypeError:
        return [x]

def _delete_marker_if_exists(track, frame):
    m = track.markers.find_frame(frame)
    if m:
        track.markers.delete_frame(frame)

def remove_segment_boundary_keys(track_or_tracks, only_if_keyed=True):
    """
    Entfernt Keyframes direkt am Start/Ende jedes zusammenhängenden Segments.
    Standard: nur löschen, wenn der Marker wirklich 'is_keyed' ist.
    """
    for track in _iter_tracks(track_or_tracks):
        if not hasattr(track, "markers") or not track.markers:
            continue

        for start, end in get_track_segments(track):
            # Start
            m = track.markers.find_frame(start)
            if m and (not only_if_keyed or getattr(m, "is_keyed", False)):
                track.markers.delete_frame(start)

            # Ende
            m = track.markers.find_frame(end)
            if m and (not only_if_keyed or getattr(m, "is_keyed", False)):
                track.markers.delete_frame(end)

def remove_keyed_outside_segments(track_or_tracks):
    """
    Falls Blender irgendwo noch vereinzelt KEYs hat, die GAR NICHT in Segmenten liegen,
    werden die entfernt (siehe Screenshot-Fälle).
    """
    for track in _iter_tracks(track_or_tracks):
        if not getattr(track, "markers", None):
            continue

        # Alle Segment-Frames einsammeln
        seg_frames = set()
        for s, e in get_track_segments(track):
            seg_frames.update(range(s, e + 1))

        # Keyed-Marker außerhalb der Segmente löschen
        to_delete = [m.frame for m in track.markers
                     if getattr(m, "is_keyed", False) and m.frame not in seg_frames]
        for f in to_delete:
            track.markers.delete_frame(f)
