def delete_marker(marker):
    """Marker entfernen oder stumm schalten.

    Direktes Löschen einzelner MovieTrackingMarker per API ist limitiert.
    Als pragmatische Lösung markieren wir den Marker als mute.
    """
    marker.mute = True
