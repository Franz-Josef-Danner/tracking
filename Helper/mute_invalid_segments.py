from .process_marker_path import get_track_segments

def _to_iter(x):
    # macht aus Einzelobjekt oder bpy_prop_collection eine Liste
    try:
        return list(x)
    except TypeError:
        return [x]

def mute_invalid_segments(track_or_tracks, scene_end):
    """
    Mute:
    - Marker, die nicht zu einem >=2-Frames-Segment gehören
    - Marker am Track-Anfang
    - Alle Marker NACH dem letzten gültigen Segment
    """
    tracks = _to_iter(track_or_tracks)

    for track in tracks:
        segments = get_track_segments(track)
        if not segments:
            continue

        # sicherheitshalber sortieren
        segments = sorted(segments, key=lambda se: se[0])

        # gültige Frames (nur Segmente mit Länge >= 2)
        valid_frames = set()
        for start, end in segments:
            if end - start + 1 >= 2:
                valid_frames.update(range(start, end + 1))

        first_frame = min((m.frame for m in track.markers), default=None)
        last_valid_frame = max(end for _, end in segments)

        for marker in track.markers:
            f = marker.frame
            if (
                (first_frame is not None and f == first_frame) or
                f not in valid_frames or
                f > last_valid_frame
            ):
                marker.mute = True
