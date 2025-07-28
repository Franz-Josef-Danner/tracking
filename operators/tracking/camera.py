import bpy

class CLIP_OT_camera_solve(bpy.types.Operator):
    bl_idname = "clip.camera_solve"
    bl_label = "Kamera solve"
    bl_description = "Löst die Kamera anhand des aktuellen Clips"

    def execute(self, context):
        clip = context.space_data.clip
        if clip is None:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}
        bpy.ops.clip.solve_camera()
        self.report({'INFO'}, "Camera solve complete.")
        return {'FINISHED'}


operator_classes = (
    CLIP_OT_camera_solve,
)
