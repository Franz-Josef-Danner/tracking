def process_marker_path(track, from_frame, direction, action="mute", mute=True):
    """
    Führt eine Aktion auf Markern eines Tracks ab einem bestimmten Frame aus.
    direction: 'forward' (>= from_frame) oder 'backward' (<= from_frame)
    action: 'mute' oder 'delete'
    """
    if not track or not getattr(track, "markers", None):
        return

    if direction == "forward":
        relevant = [m for m in track.markers if m.frame >= from_frame]
    elif direction == "backward":
        relevant = [m for m in track.markers if m.frame <= from_frame]
    else:
        return

    if action == "mute":
        for m in relevant:
            m.mute = mute
    elif action == "delete":
        # nicht über die Sammlung iterieren, während wir löschen
        for f in [m.frame for m in relevant]:
            track.markers.delete_frame(f)


def get_track_segments(track):
    """
    Gibt zusammenhängende Segmente als (start, end)-Tupel zurück.
    Ein Segment hat keine Frame-Lücken (>1 Frame Abstand).
    """
    markers = getattr(track, "markers", None)
    if not markers:
        return []

    frames = sorted(m.frame for m in markers)
    if not frames:
        return []

    segs = []
    start = prev = frames[0]
    for f in frames[1:]:
        if f - prev > 1:
            segs.append((start, prev))
            start = f
        prev = f
    segs.append((start, prev))
    return segs
