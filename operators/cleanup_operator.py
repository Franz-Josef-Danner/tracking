import bpy
from ..helpers.cleanup_tracks import cleanup_error_tracks


class CLIP_OT_cleanup_tracks(bpy.types.Operator):
    bl_idname = "clip.cleanup_tracks"
    bl_label = "Cleanup Error Tracks"
    bl_description = "Bereinigt automatisch alle fehlerhaften Tracks"

    @classmethod
    def poll(cls, context):
        return (
            context.area
            and context.area.type == "CLIP_EDITOR"
            and getattr(context.space_data, "clip", None)
        )

    def execute(self, context):
        clip = getattr(context.space_data, "clip", None)
        if clip is None:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}
        cleanup_error_tracks(context.scene, clip)
        self.report({'INFO'}, "Bereinigung abgeschlossen")
        return {'FINISHED'}

