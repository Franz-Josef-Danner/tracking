import bpy

class CLIP_OT_set_test_value(bpy.types.Operator):
    bl_idname = "clip.set_test_value"
    bl_label = "Test value"
    bl_description = "Berechnet Marker-Zielwerte anhand von 'marker_frame'"

    def execute(self, context):
        scene = context.scene
        marker_basis = getattr(scene, "marker_frame", None)

        if marker_basis is None:
            self.report({'WARNING'}, "Eingabewert 'marker_frame' nicht gefunden.")
            return {'CANCELLED'}

        # Grundwerte berechnen
        marker_plus = marker_basis / 3
        marker_adapt = marker_plus
        max_marker = int(marker_adapt * 1.1)
        min_marker = int(marker_adapt * 0.9)

        # Erweiterte Zielwertberechnung (z.B. normierter Wert)
        # Beispiel: marker_value = gewichtete Mischung + Normalisierung
        # Du kannst diese Formel gerne anpassen
        marker_value = (marker_adapt + max_marker + min_marker) / 3

        # Optional: Speicherung im Szene-Objekt oder Custom Property
        scene["marker_adapt"] = marker_adapt
        scene["marker_max"] = max_marker
        scene["marker_min"] = min_marker
        scene["marker_value"] = marker_value

        self.report({'INFO'}, f"Marker-Werte berechnet: Basis={marker_basis:.2f}, Wert={marker_value:.2f}")
        return {'FINISHED'}
