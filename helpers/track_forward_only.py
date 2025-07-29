import bpy


def track_forward_only(start_frame: int, end_frame: int) -> None:
    """Führt nur vorwärts Tracking durch (für Track Nr. 2)."""
    scene = bpy.context.scene
    scene.frame_current = start_frame
    print(f"[Track Forward Only] start {start_frame} end {end_frame}")
    bpy.ops.clip.track_markers(backwards=False, sequence=True)
    print("[Track Forward Only] done")
