import bpy

def find_low_marker_frame(clip, frame_start=None, frame_end=None):
    tracking = clip.tracking
    tracks = tracking.tracks
    scene = bpy.context.scene

    # Verwende den zentralen Marker-Basiswert aus der Szene
    marker_basis = scene.get("marker_adapt", 20)
    min_marker = scene.get("min_marker", int(marker_basis * 0.9))

    if frame_start is None:
        frame_start = clip.frame_start
    if frame_end is None:
        frame_end = clip.frame_duration

    print(f"[MarkerCheck] Erwartete Marker pro Frame (marker_basis={marker_basis}, min_marker={min_marker})")

    for frame in range(frame_start, frame_end + 1):
        count = 0
        for track in tracks:
            marker = track.markers.find_frame(frame)
            if marker:
                count += 1

        print(f"[MarkerCheck] Frame {frame}: {count} aktive Marker")

        if count < min_marker:
            print(f"[MarkerCheck] → Zu wenige Marker in Frame {frame}")
            return frame

    print("[MarkerCheck] Kein Frame mit zu wenigen Markern gefunden.")
    return None
