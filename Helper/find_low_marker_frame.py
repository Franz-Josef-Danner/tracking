import bpy

def find_low_marker_frame(context, marker_per_frame=5):
    scene = context.scene
    clip = context.space_data.clip
    tracking = clip.tracking
    tracks = tracking.tracks

    frame_start = scene.frame_start
    frame_end = scene.frame_end

    for frame in range(frame_start, frame_end + 1):
        count = 0
        for track in tracks:
            if track.mute:
                continue
            marker = track.markers.find_frame(frame)
            if marker:
                count += 1

        print(f"[MarkerCheck] Frame {frame}: {count} active markers")
        if count < marker_per_frame:
            print(f"[MarkerCheck] → First frame with fewer markers than {marker_per_frame}: {frame}")
            return frame

    print("[MarkerCheck] No frame found with fewer markers.")
    return None
