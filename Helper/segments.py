# Helper/segments.py
def track_has_internal_gaps(track) -> bool:
    """True, wenn im Track mind. eine Lücke von >=1 fehlenden Frames existiert (O(n))."""
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
            diff = int(f) - int(prev)
            missing = diff - 1               # Anzahl fehlender Frames zwischen prev und f
            if missing >= 1:                 # schon 1 fehlender Frame ⇒ interne Lücke
                return True
            prev = f
        return False
    except Exception as e:
        return False


def get_track_segments(track):
    """Liefert zusammenhängende Frame-Segmente (defensiv).
    Segmentbruch, sobald >=1 Frame fehlt (Gap)."""
    markers = getattr(track, "markers", None)
    if not markers:
        return []

    frames = sorted({int(getattr(m, "frame", -1)) for m in markers})
    if not frames:
        return []

    segments, current = [], [frames[0]]
    for i in range(1, len(frames)):
        diff = frames[i] - frames[i - 1]
        missing = diff - 1
        if missing >= 1:                     # ein fehlender Frame reicht für Segmentbruch
            segments.append(current)
            current = [frames[i]]
        else:
            current.append(frames[i])
    segments.append(current)
    return segments
