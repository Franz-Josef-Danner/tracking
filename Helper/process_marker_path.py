def process_marker_path(track, from_frame, direction, action="mute", mute=True):
    """
    Führt eine Aktion auf Markern eines Tracks ab einem bestimmten Frame aus.

    Args:
        track: Der Track, auf dem gearbeitet wird.
        from_frame: Start-Frame für die Aktion.
        direction: 'forward' oder 'backward'.
        action: 'mute' oder 'delete'.
        mute: Nur relevant bei action='mute'. Gibt an, ob gemutet oder entmutet werden soll.
    """
    if not track or not track.markers:
        return

    if direction == "forward":
        relevant_markers = [m for m in track.markers if m.frame >= from_frame]
    elif direction == "backward":
        relevant_markers = [m for m in track.markers if m.frame <= from_frame]
    else:
        return

    if action == "mute":
        for marker in relevant_markers:
            marker.mute = mute

    elif action == "delete":
        # Wichtig: Nicht direkt iterieren und löschen – sonst Absturzgefahr
        frames_to_delete = [m.frame for m in relevant_markers]
        for frame in frames_to_delete:
            track.markers.delete_frame(frame)


def get_track_segments(track):
    """
    Liefert Segmente (start, end) anhand *echter* Keyframes, nicht der geschätzten Frames.
    Fallback: wenn 'is_keyed' nicht existiert oder keine Keyframes gefunden werden,
    benutzen wir alle Frames wie bisher.
    """
    # 1) nur echte Keyframes einsammeln (falls verfügbar)
    keyed = [m.frame for m in track.markers if getattr(m, "is_keyed", False)]
    frames = sorted(set(keyed)) if keyed else sorted({m.frame for m in track.markers})

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

