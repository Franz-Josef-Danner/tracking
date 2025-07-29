import bpy
from ...helpers.utils import update_frame_display


def execute(self, context):
    """Track selected markers backwards and then forwards."""
    clip = context.space_data.clip
    if not clip:
        self.report({'WARNING'}, "Kein Clip geladen")
        return {'CANCELLED'}

    if not any(t.select for t in clip.tracking.tracks):
        self.report({'WARNING'}, "Keine Tracks ausgewählt")
        return {'CANCELLED'}

    scene = context.scene
    original_start = scene.frame_start
    original_end = scene.frame_end
    current = scene.frame_current

    if not bpy.ops.clip.track_markers.poll():
        self.report({'WARNING'}, "Tracking nicht möglich")
        return {'CANCELLED'}

    scene.frame_start = original_start
    scene.frame_end = current
    bpy.ops.clip.track_markers(backwards=True, sequence=True)

    scene.frame_start = current
    scene.frame_end = original_end
    scene.frame_current = current
    update_frame_display(context)
    bpy.ops.clip.track_markers(backwards=False, sequence=True)

    scene.frame_start = original_start
    scene.frame_end = original_end
    scene.frame_current = current
    update_frame_display(context)

    return {'FINISHED'}
