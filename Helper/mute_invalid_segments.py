def mute_invalid_segments(track, scene_end):
    """
    Mute alle Marker, die:
    - nicht zu einem ≥2 Frames langen Segment gehören
    - oder am Track-Anfang liegen
    - oder nach dem letzten gültigen Frame liegen
    """
    segments = get_track_segments(track)
    if not segments:
        return

    valid_frames = set()
    for segment in segments:
        if len(segment) >= 2:
            valid_frames.update(segment)

    first_frame = min((m.frame for m in track.markers), default=None)
    last_valid_frame = segments[-1][-1]

    for marker in track.markers:
        f = marker.frame
        if f not in valid_frames or f == first_frame or f > last_valid_frame:
            marker.mute = True
