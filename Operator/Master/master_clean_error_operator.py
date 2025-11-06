# Operator/Helper/clean_error_operator.py
import bpy
from bpy.types import Operator, Context

class KAISERLICHTRACKER_OT_clean_error_operator(Operator):
    """Führt den internen Clean Error aus (bpy.ops.clip.clean_error)"""
    bl_idname = "kaiserlich_tracker.clean_error_operator"
    bl_label = "Clean Error (Direct)"
    bl_description = "Löscht oder selektiert Tracks mit hohem Reprojection Error"
    bl_options = {'REGISTER', 'UNDO'}

    # --- Parameter ---
    threshold: bpy.props.FloatProperty(
        name="Clean Error Threshold",
        description="Reprojection Error Grenze für Cleanup",
        default=20.0,
        min=0.0,
        soft_max=100.0
    )

    action: bpy.props.EnumProperty(
        name="Cleanup Action",
        description="Art der Bereinigung",
        items=[
            ('SELECT', "Select", "Markiert ungenaue Tracks"),
            ('DELETE_TRACK', "Delete Track", "Löscht fehlerhafte Tracks"),
            ('DELETE_SEGMENTS', "Delete Segments", "Löscht fehlerhafte Segmente")
        ],
        default='DELETE_TRACK'
    )

    def execute(self, context: Context):
        # Aktiver Clip prüfen
        clip = getattr(context.space_data, "clip", None)
        if not clip:
            self.report({'ERROR'}, "Kein aktiver MovieClip gefunden.")
            return {'CANCELLED'}

        # Zugriff auf TrackingSettings
        settings = clip.tracking.settings
        if not settings:
            self.report({'ERROR'}, "TrackingSettings nicht verfügbar.")
            return {'CANCELLED'}

        # Parameter setzen
        settings.clean_action = self.action
        settings.clean_error = self.threshold

        # Operator im Clip-Kontext ausführen
        try:
            bpy.ops.clip.clean_error('INVOKE_DEFAULT')
        except Exception as e:
            self.report({'ERROR'}, f"Clean Error fehlgeschlagen: {e}")
            return {'CANCELLED'}

        self.report({'INFO'}, f"Clean Error ausgeführt ({self.action}, Threshold={self.threshold:.3f})")
        return {'FINISHED'}


# Registrierung
def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_clean_error_operator)

def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_clean_error_operator)

if __name__ == "__main__":
    register()
