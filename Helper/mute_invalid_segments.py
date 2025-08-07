from .process_marker_path import get_track_segments

def mute_invalid_segments(track_or_tracks, scene_end):
    """
    Mute:
    - Marker, die nicht zu einem >=2-Frames-Segment gehören
    - Marker am Track-Anfang
    - Marker nach dem letzten gültigen Frame
    """
    tracks = track_or_tracks if isinstance(track_or_tracks, (list, tuple)) else [track_or_tracks]

    for track in tracks:
        segments = get_track_segments(track)
        if not segments:
            continue

        # gültige Frames aus Segmenten mit Länge >=2
        valid_frames = set()
        for (start, end) in segments:
            if end - start + 1 >= 2:
                valid_frames.update(range(start, end + 1))

        first_frame = min((m.frame for m in track.markers), default=None)
        last_valid_frame = segments[-1][1]

        for marker in track.markers:
            f = marker.frame
            if (first_frame is not None and f == first_frame) or f > last_valid_frame or f not in valid_frames:
                marker.mute = True
