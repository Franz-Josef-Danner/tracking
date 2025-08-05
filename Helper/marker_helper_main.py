import bpy

class CLIP_OT_marker_helper_main(bpy.types.Operator):
    bl_idname = "clip.marker_helper_main"
    bl_label = "Marker-Helfer-Haupt berechnen"
    bl_description = "Berechnet Marker-haupt-Zielwerte anhand von 'marker/Frame'"

    def execute(self, context):
        scene = context.scene
        marker_basis = getattr(scene, "marker_frame", None)
        if marker_basis is None:
            self.report({'WARNING'}, "Eingabewert 'marker_frame' nicht gefunden.")
            return {'CANCELLED'}

        marker_plus = marker_basis * 4
        marker_adapt = marker_plus
        max_marker = int(marker_adapt * 1.1)
        min_marker = int(marker_adapt * 0.9)

        self.report({'INFO'}, 
            f"Marker Zielwert: {marker_adapt}, Max: {max_marker}, Min: {min_marker}"
        )
        return {'FINISHED'}
