import bpy

def find_first_weak_frame(context):
    """
    Gibt den ersten Frame im aktiven Clip zurück, 
    der weniger Marker hat als scene.kaiserlich_markers_per_frame.
    Setzt außerdem scene.frame_current auf diesen Frame.
    Gibt None zurück, wenn kein Frame die Bedingung erfüllt.
    """

    scene = context.scene
    target_markers = scene.kaiserlich_markers_per_frame

    # Sicherstellen, dass wir im Movie Clip Editor mit aktivem Clip sind
    space_data = context.space_data
    if not space_data or not hasattr(space_data, 'clip') or not space_data.clip:
        print("❌ Kein aktiver Movie Clip im Editor gefunden.")
        return None

    clip = space_data.clip
    tracking = clip.tracking

    # Dictionary: {frame: marker_count}
    markers_per_frame = {}

    for track in tracking.tracks:
        for marker in track.markers:
            frame = marker.frame
            markers_per_frame.setdefault(frame, 0)
            markers_per_frame[frame] += 1

    # Frames sortieren und ersten mit zu wenig Markern finden
    for frame in sorted(markers_per_frame):
        count = markers_per_frame[frame]
        if count < target_markers:
            print(f"✅ Erster schwacher Frame: {frame} mit {count} Markern (Ziel: {target_markers})")
            scene.frame_current = frame
            return frame

    print(f"⚠️ Kein Frame gefunden mit weniger als {target_markers} Markern.")
    return None
