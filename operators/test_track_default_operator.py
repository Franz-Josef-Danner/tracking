import bpy

class TRACK_OT_test_default(bpy.types.Operator):
    bl_idname = "tracking.test_default"
    bl_label = "Test Default"
    bl_description = "Führt den Operator für Default Tracking Settings aus"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.space_data is not None and context.space_data.type == 'CLIP_EDITOR'

    def execute(self, context):
        try:
            bpy.ops.clip.track_default_settings()
        except Exception as e:
            self.report({'ERROR'}, f"Fehler beim Ausführen von track_default_settings: {e}")
            return {'CANCELLED'}
        return {'FINISHED'}
