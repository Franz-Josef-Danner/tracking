# Helper/segments.py
def track_has_internal_gaps(track) -> bool:
    """True, wenn im Track Frame-Lücken >1 existieren (defensiv, O(n))."""
    try:
        markers = getattr(track, "markers", None)
        if not markers:
            return False

        # Einmalig sortierte, deduplizierte Frames (als int)
        frames = sorted({int(getattr(m, "frame", -1)) for m in markers})
        if len(frames) < 2:  # <3 ist unnötig restriktiv
            return False

        prev = frames[0]
        for f in frames[1:]:
            if int(f) - int(prev) > 1:
                return True
            prev = f
        return False
    except Exception as e:
        return False


def get_track_segments(track):
    """Liefert zusammenhängende Frame-Segmente (defensiv)."""
    markers = getattr(track, "markers", None)
    if not markers:
        return []

    frames = sorted({int(getattr(m, "frame", -1)) for m in markers})
    if not frames:
        return []

    segments, current = [], [frames[0]]
    for i in range(1, len(frames)):
        if frames[i] - frames[i - 1] == 1:
            current.append(frames[i])
        else:
            segments.append(current)
            current = [frames[i]]
    segments.append(current)
    return segments
