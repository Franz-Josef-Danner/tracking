def delete_selected_markers(frames_track):
    """
    Löscht selektierte Marker aus den übergebenen Tracks.

    :param frames_track: Liste von MovieTrackingTrack-Objekten
    """
    for track in frames_track:
        # Marker kopieren, um während der Iteration löschen zu können
        markers_to_delete = [marker.frame for marker in track.markers if marker.select]
        for frame in markers_to_delete:
            track.markers.remove(frame)
