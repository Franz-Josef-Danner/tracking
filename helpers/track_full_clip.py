import bpy


def track_full_clip():
    """Track the clip forward if possible."""
    if bpy.ops.clip.track_full.poll():
        bpy.ops.clip.track_full(silent=True)
