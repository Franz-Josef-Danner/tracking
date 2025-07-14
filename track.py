"""Functions to track markers bidirectionally."""

import bpy


def track_bidirectional(context, tracks):
    area = next((a for a in context.screen.areas if a.type == 'CLIP_EDITOR'), None)
    if not area:
        return
    with context.temp_override(area=area):
        bpy.ops.clip.track_markers('INVOKE_DEFAULT', backwards=False)
        bpy.ops.clip.track_markers('INVOKE_DEFAULT', backwards=True)
