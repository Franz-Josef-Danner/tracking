import bpy

def get_first_low_marker_frame(context):
    scene = context.scene
    clip = context.space_data.clip
    tracking = clip.tracking
    tracks = tracking.tracks

    frame_start = scene.frame_start
    frame_end = scene.frame_end

    # Hole Wert aus Szene, fallback = 5
    marker_per_frame = scene.get("marker_per_frame", 5)
    print(f"[MarkerCheck] Erwartete Marker pro Frame: {marker_per_frame}")

    for frame in range(frame_start, frame_end + 1):
        count = 0
        for track in tracks:
            if track.mute:
                continue
            marker = track.markers.find_frame(frame)
            if marker:
                count += 1

        print(f"[MarkerCheck] Frame {frame}: {count} aktive Marker")
        if count < marker_per_frame:
            print(f"[MarkerCheck] → Zu wenige Marker in Frame {frame}")
            return frame

    print("[MarkerCheck] Kein Frame mit zu wenigen Markern gefunden.")
    return None
