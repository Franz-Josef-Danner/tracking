import bpy

from .bidirectional_tracking_operator import TrackingController


class TRACKING_OT_delete_short_tracks(bpy.types.Operator):
    """Löscht kurze Tracks anhand des Frames/Track-Werts"""

    bl_idname = "tracking.delete_short_tracks"
    bl_label = "Kurze Tracks löschen"
    bl_options = {'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.space_data and getattr(context.space_data, 'clip', None)

    def execute(self, context):
        controller = TrackingController(context)
        controller.cleanup_short_tracks()
        return {'FINISHED'}
