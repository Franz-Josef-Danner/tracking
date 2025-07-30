import bpy
from ..helpers.test_marker_base import test_marker_base


class TRACKING_OT_test_marker_base(bpy.types.Operator):
    """Berechnet Marker-Basiswerte f\u00fcr Tests"""
    bl_idname = "tracking.test_marker_base"
    bl_label = "Test Basis"
    bl_description = "Berechnet Testwerte aus Marker/Frame"

    @classmethod
    def poll(cls, context):
        return context.space_data and context.space_data.clip

    def execute(self, context):
        scene = context.scene
        values = test_marker_base(context)
        scene["marker_plus"] = values["marker_plus"]
        scene["marker_adapt"] = values["marker_adapt"]
        scene["max_marker"] = values["max_marker"]
        scene["min_marker"] = values["min_marker"]
        self.report(
            {'INFO'},
            f"marker_basis={values['marker_basis']}, adapt={int(values['marker_adapt'])}, min={int(values['min_marker'])}, max={int(values['max_marker'])}"
        )
        return {'FINISHED'}

