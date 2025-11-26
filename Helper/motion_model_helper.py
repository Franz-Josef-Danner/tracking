import bpy

def apply_motion_model(
    track: 'bpy.types.MovieTrackingTrack',
    modeled_positions: list[tuple[int, tuple[float, float]]],
    motion_model: str = 'Loc'
) -> None:
    """
    Setzt für einen Track die berechneten (modellierten) Marker-Positionen
    und schreibt am Ende das gewünschte Motion Model auf den Track.
    Parallel werden Debug-Ausgaben pro Marker erzeugt.
    """

    markers = track.markers

    for frame, coords in modeled_positions:
        marker = markers.find_frame(frame, exact=True)

        if marker is None:
            continue

        x, y = coords

        old_x = marker.co.x
        old_y = marker.co.y


        marker.co = (x, y)

    # Motion Model am Track setzen
    track.motion_model = motion_model

