import bpy


def track_bidirectional(start_frame, end_frame):
    """Führt bidirektionales Tracking von start bis end aus."""
    scene = bpy.context.scene
    scene.frame_start = start_frame
    scene.frame_end = end_frame

    print(f"[Track Bidirectional] start {start_frame} end {end_frame}")
    bpy.ops.clip.track_partial(backwards=True)
    bpy.ops.clip.track_partial(backwards=False)
    print(f"[Track Bidirectional] done")


def track_forward_only(start_frame, end_frame):
    """Führt nur vorwärts Tracking aus."""
    scene = bpy.context.scene
    scene.frame_start = start_frame
    scene.frame_end = end_frame

    print(f"[Track Forward Only] start {start_frame} end {end_frame}")
    bpy.ops.clip.track_partial(backwards=False)
    print(f"[Track Forward Only] done")
