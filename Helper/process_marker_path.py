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
