import bpy

class CLIP_OT_cleanup_operator(bpy.types.Operator):
    bl_idname = "clip.cleanup_operator"
    bl_label = "Cleanup Tracks"
    bl_description = "Bereinigt Tracking-Spuren"

    def execute(self, context):
        self.report({'INFO'}, "Cleanup Operator ausgefuehrt")
        return {'FINISHED'}

operator_classes = (
    CLIP_OT_cleanup_operator,
)
