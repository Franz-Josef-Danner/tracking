import bpy

def apply_motion_model(track: 'bpy.types.MovieTrackingTrack',
                       modeled_positions: list[tuple[int, tuple[float, float]]],
                       motion_model: str = 'Loc') -> None:
  
    markers = track.markers
    for frame, coords in modeled_positions:
        marker = markers.find_frame(frame, exact=True)
        if marker is None:
            continue
        x, y = coords

        marker.co = (x, y)

    track.motion_model = motion_model
    print(f"[MotionModel][APPLY] Track='{track.name}' -> Model={motion_model}")
