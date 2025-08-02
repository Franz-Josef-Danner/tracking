import bpy


class TRACKING_OT_marker_basis_values(bpy.types.Operator):
    bl_idname = "tracking.marker_basis_values"
    bl_label = "Marker Basis Value"
    bl_description = (
        "Berechnet marker_plus, marker_adapt, min_marker, max_marker aus marker_basis"
    )

    @classmethod
    def poll(cls, context):
        return context.space_data and context.space_data.clip

    def execute(self, context):
        scene = context.scene

        marker_basis = scene.get("marker_basis", 20)

        marker_plus = marker_basis / 3
        marker_adapt = marker_plus
        max_marker = marker_adapt + 1
        min_marker = marker_adapt - 1

        scene["marker_plus"] = marker_plus
        scene["marker_adapt"] = marker_adapt
        scene["max_marker"] = max_marker
        scene["min_marker"] = min_marker

        self.report(
            {'INFO'},
            f"marker_basis={marker_basis}, adapt={int(marker_adapt)}, min={int(min_marker)}, max={int(max_marker)}"
        )
        return {'FINISHED'}
