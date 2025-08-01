import bpy
from .test_marker_base import test_marker_base


class TRACKING_OT_test_marker_base(bpy.types.Operator):
    """Hilfsoperator zum Ausgeben von Markerwerten."""

    bl_idname = "tracking.test_marker_base"
    bl_label = "Test Marker Base"

    def execute(self, context):
        values = test_marker_base(context)
        print(f"Markerwerte: {values}")
        return {'FINISHED'}

