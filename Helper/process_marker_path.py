def get_track_segments(track):
    """
    Liefert Segmente (start, end) anhand ALLER Markerframes.
    Keyframes werden NICHT zur Segmentbildung benutzt.
    """
    frames = sorted({m.frame for m in track.markers})
    if not frames:
        return []

    segments = []
    start = prev = frames[0]
    for f in frames[1:]:
        if f - prev > 1:
            segments.append((start, prev))
            start = f
        prev = f
    segments.append((start, prev))
    return segments
