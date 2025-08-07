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
    to_process = []
    for marker in track.markers:
        if (direction == 'forward' and marker.frame >= from_frame) or \
           (direction == 'backward' and marker.frame <= from_frame):
            to_process.append(marker)

    for marker in to_process:
        if action == "mute":
            marker.mute = mute
        elif action == "delete":
            track.markers.delete_frame(marker.frame)
