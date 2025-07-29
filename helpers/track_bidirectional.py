import bpy


def track_bidirectional(start_frame: int, end_frame: int) -> None:
    """Führt bidirektionales Tracking durch (für Track Nr. 1)."""
    scene = bpy.context.scene
    scene.frame_current = start_frame
    print(f"[Track Bidirectional] start {start_frame} end {end_frame}")
    bpy.ops.clip.track_markers(backwards=True, sequence=True)
    bpy.ops.clip.track_markers(backwards=False, sequence=True)
    print("[Track Bidirectional] done")
