import bpy
from .update_frame_display import update_frame_display


def track_markers_range(scene, start, end, current, backwards):
    """Run clip.track_markers for ``start`` to ``end``."""
    scene.frame_start = start
    scene.frame_end = end
    if not backwards:
        scene.frame_current = current
        update_frame_display()
    bpy.ops.clip.track_markers(backwards=backwards, sequence=True)
