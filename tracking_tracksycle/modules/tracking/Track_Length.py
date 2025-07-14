"""Helper for computing track length."""



def get_track_length(track):
    """Return the length of a tracking track."""
    frames = [m.frame for m in track.markers]
    return max(frames) - min(frames) if frames else 0

