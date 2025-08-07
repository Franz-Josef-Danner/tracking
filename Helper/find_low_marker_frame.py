import bpy

def find_low_marker_frame(clip, marker_basis=20, frame_start=None, frame_end=None):
    tracking = clip.tracking
    tracks = tracking.tracks

    if frame_start is None:
        frame_start = clip.frame_start
    if frame_end is None:
        frame_end = bpy.context.scene.frame_end


    for frame in range(frame_start, frame_end + 1):
        count = 0
        for track in tracks:
            marker = track.markers.find_frame(frame)
            if marker:
                count += 1


        if count < marker_basis:
            print(f"[MarkerCheck] → Zu wenige Marker in Frame {frame}")
            return frame

    return None
