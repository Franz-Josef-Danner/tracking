import bpy
from ..Helper import bootstrap, snapshot

class KAISERLICH_OT_detect_cyclus(bpy.types.Operator):
    bl_idname = "kaiserlich.detect_cycle"  # ID bleibt technisch gleich für Kompatibilität
    bl_label = "Detect Cyclus"
    bl_description = "Führt den Erkennungs-Cyclus aus"

    def execute(self, context):
        scene = context.scene
        ef = scene.kaiserlich_marker_per_frame
        # Snapshot der aktuell aktiven Marker
        markers = snapshot.capture_current_frame_markers(context)
        # Übergabe an Bootstrap Logik
        bootstrap.run(context, ef)
        self.report({'INFO'}, f"Bootstrap & Snapshot: {len(markers)} Marker, ef={ef}")
        return {'FINISHED'}

classes = [KAISERLICH_OT_detect_cyclus]

def register():
    for cls in classes:
        try:
            bpy.utils.register_class(cls)
        except Exception:
            pass

def unregister():
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass
