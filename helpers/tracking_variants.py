import bpy


def track_bidirectional(start_frame: int, end_frame: int) -> None:
    """Führt bidirektionales Tracking durch (für Track Nr. 1)."""

    scene = bpy.context.scene
    scene.frame_current = start_frame
    print(f"[Track Bidirectional] start {start_frame} end {end_frame}")

    # Track zuerst rückwärts, dann vorwärts
    bpy.ops.clip.track_markers(backwards=True)
    bpy.ops.clip.track_markers(backwards=False)

    print("[Track Bidirectional] done")


def track_forward_only(start_frame: int, end_frame: int) -> None:
    """Führt nur vorwärts Tracking durch (für Track Nr. 2)."""

    scene = bpy.context.scene
    scene.frame_current = start_frame
    print(f"[Track Forward Only] start {start_frame} end {end_frame}")

    bpy.ops.clip.track_markers(backwards=False)

    print("[Track Forward Only] done")
