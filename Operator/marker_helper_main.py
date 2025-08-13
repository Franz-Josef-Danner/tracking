import bpy

class CLIP_OT_marker_helper_main(bpy.types.Operator):
    bl_idname = "clip.marker_helper_main"
    bl_label = "Marker Helper Main"
    bl_description = "Berechnet Marker-Zielwerte und startet die Kette"

    factor: bpy.props.IntProperty(
        name="Faktor",
        description="Multiplikator für marker_basis → marker_adapt",
        default=4, min=1, max=999
    )

    def execute(self, context):
        scene = context.scene

        # Basis lesen (Fallback 25)
        marker_basis = int(scene.get("marker_basis", 25))
        marker_adapt = int(marker_basis * self.factor * 0.9)
        marker_min   = int(marker_adapt * 0.9)
        marker_max   = int(marker_adapt * 1.1)

        # Konsistente Keys setzen (beide Varianten, damit Downstream sicher liest)
        scene["marker_adapt"] = marker_adapt
        scene["marker_min"]   = marker_min
        scene["marker_max"]   = marker_max
        # Legacy/Fallback (falls Altcode diese Keys liest)
        scene["min_marker"]   = marker_min
        scene["max_marker"]   = marker_max

        self.report({'INFO'}, f"Marker: adapt={marker_adapt}, min={marker_min}, max={marker_max}")
        print(f"[MarkerHelper] adapt={marker_adapt}, min={marker_min}, max={marker_max} → Übergabe an main_to_adapt")

        # Nächster Schritt der Kette
        try:
            res = bpy.ops.clip.launch_find_low_marker_frame_with_adapt('INVOKE_DEFAULT', factor=int(self.factor))
            print(f"[MarkerHelper] → launch_find_low_marker_frame_with_adapt: {res}")
        except Exception as e:
            self.report({'ERROR'}, f"main_to_adapt konnte nicht gestartet werden: {e}")
            return {'CANCELLED'}

        return {'FINISHED'}


# Registration (falls lokal registriert wird)
classes = (CLIP_OT_marker_helper_main,)
def register():
    for cls in classes:
        bpy.utils.register_class(cls)
def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
