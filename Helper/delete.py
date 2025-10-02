def delete_marker(marker):
    track = getattr(marker, 'track', None)
    if track is None:
        return
    try:
        track.markers.remove(marker)
    except Exception:
        pass
