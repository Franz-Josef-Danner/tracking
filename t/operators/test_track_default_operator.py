import bpy
from . import test_track_default_settings


class TRACK_OT_test_default(bpy.types.Operator):
    bl_idname = "track.test_default"
    bl_label = "Test Default"
    bl_description = "Führe Test Default Settings aus"

    def execute(self, context):
        test_track_default_settings.main()
        return {'FINISHED'}
