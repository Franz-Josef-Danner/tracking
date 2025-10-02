import bpy

def delete_marker(track_marker_tuple, frame: int):
    track, marker = track_marker_tuple
    try:
        track.markers.delete_frame(frame)
    except Exception as e:
        print(f"Fehler beim Löschen Marker @Frame {frame}: {e}")
