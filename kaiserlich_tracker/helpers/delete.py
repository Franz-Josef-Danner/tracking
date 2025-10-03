def delete_marker(marker):
    try:
        track = marker.track
        track.markers.delete_frame(marker.frame)
    except Exception:
        # Silent fail – Marker vielleicht schon gelöscht
        pass
