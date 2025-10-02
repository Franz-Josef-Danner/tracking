import bpy

def snapshot_markers(frame: int):
    """Gibt Liste der aktuell existierenden Marker (MovieTrackingMarker) des aktuellen Tracks zurück."""
    markers = []
    clip = bpy.context.space_data.clip if bpy.context.space_data else None
    if not clip:
        return markers
    tracking = clip.tracking
    for obj in tracking.objects:
        for track in obj.tracks:
            marker = track.markers.find_frame(frame)
            if marker:
                markers.append((track, marker))
    return markers
