def select_short_tracks(frames_track, min_track_length=10):
    """
    Selektiert alle Tracks in frames_track, deren Tracking-Länge unter min_track_length liegt.
    Die Tracking-Länge wird über die aktiven Marker (nicht gemutete) bestimmt.

    :param frames_track: Liste von MovieTrackingTrack (z. B. clip.tracking.tracks)
    :param min_track_length: Mindestanzahl von aktiven Markern
    """
    selected_count = 0
    for track in frames_track:
        # Zähle aktive Marker
        track_length = sum(1 for marker in track.markers if not marker.mute)
        if track_length < min_track_length:
            track.select = True
            selected_count += 1
        else:
            track.select = False  # optional
    return selected_count
