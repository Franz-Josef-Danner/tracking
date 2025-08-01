import bpy

class TRACK_OT_test_combined(bpy.types.Operator):
    bl_idname = "track.test_combined"
    bl_label = "Test Marker + Default"
    bl_description = "Führe Test Marker Base und Test Default nacheinander aus"

    def execute(self, context):
        bpy.ops.tracking.test_marker_base()
        bpy.ops.track.test_default()
        return {'FINISHED'}
