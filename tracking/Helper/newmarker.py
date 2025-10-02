import bpy

def new_markers(frame: int, alte_marker):
    """Finde Marker die neu hinzugekommen sind (nicht in alte_marker)."""
    alt_tracks = {id(t[0]): t for t in alte_marker}
    clip = bpy.context.space_data.clip if bpy.context.space_data else None
    result = []
    if not clip:
        return result
    tracking = clip.tracking
    for obj in tracking.objects:
        for track in obj.tracks:
            marker = track.markers.find_frame(frame)
            if marker and id(track) not in alt_tracks:
                result.append((track, marker))
    return result
