import bpy
from mathutils import Vector

# Snapshot aktiver Tracking Marker im aktuellen Frame

def snapshot_active_markers(context):
    space = context.space_data
    if not space or space.type != 'CLIP_EDITOR':
        print("[Kaiserlich] Kein Movie Clip Editor aktiv – Snapshot abgebrochen")
        return []

    clip = space.clip
    if not clip:
        print("[Kaiserlich] Kein Clip geladen – Snapshot abgebrochen")
        return []

    tracking = clip.tracking
    current_frame = context.scene.frame_current

    markers_collected = []

    for track in tracking.tracks:
        # Hole Marker am aktuellen Frame
        marker = track.markers.find_frame(current_frame)
        if marker and not marker.mute:
            data = {
                'track_name': track.name,
                'frame': marker.frame,
                'co': (marker.co[0], marker.co[1]),
                'is_keyed': marker.is_keyed,
            }
            markers_collected.append(data)

    print(f"[Kaiserlich] Snapshot Frame {current_frame}: {len(markers_collected)} aktive Marker")
    return markers_collected

# Optional: globaler Zwischenspeicher
LAST_SNAPSHOT = []

def store_snapshot(context):
    global LAST_SNAPSHOT
    LAST_SNAPSHOT = snapshot_active_markers(context)
    return LAST_SNAPSHOT
