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

    # Übersicht: wie viele Marker-Positionen werden überhaupt versucht?
    print(f"[MotionModel][APPLY] Track='{track.name}'  "
          f"Model='{motion_model}'  Positions={len(modeled_positions)}")

    for frame, coords in modeled_positions:
        marker = markers.find_frame(frame, exact=True)

        if marker is None:
            # Transparente Info, dass für diesen Frame nichts gesetzt wurde
            print(f"[MotionModel][SKIP] Track='{track.name}'  "
                  f"Frame={frame}  Grund='kein Marker im Track'")
            continue

        x, y = coords

        # Alte Koordinate vor der Änderung
        old_x = marker.co.x
        old_y = marker.co.y

        # Debug-Ausgabe pro Marker / Frame
        print(
            f"[MotionModel][SET] Track='{track.name}'  "
            f"Frame={frame}  "
            f"Old=({old_x:.6f}, {old_y:.6f})  "
            f"New=({x:.6f}, {y:.6f})  "
            f"Model='{motion_model}'"
        )

        # Neue Position setzen
        marker.co = (x, y)

    # Motion Model am Track setzen
    track.motion_model = motion_model

    # Abschluss-Log, um zu sehen, was final am Track steht
    print(f"[MotionModel][DONE] Track='{track.name}'  "
          f"FinalModel='{track.motion_model}'")
