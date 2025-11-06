# Operator/Master/master_clean_error_operator.py
import bpy
from bpy.types import Operator, Context

class KAISERLICHTRACKER_OT_clean_error_operator(Operator):
    """Führt bpy.ops.clip.clean_error() mit sicherem Kontext aus"""
    bl_idname = "kaiserlich_tracker.clean_error_operator"
    bl_label = "Clean Error (Context Safe)"
    bl_options = {'REGISTER', 'UNDO'}

    threshold: bpy.props.FloatProperty(
        name="Threshold",
        description="Reprojection Error Grenze für Cleanup",
        default=20.0,
        min=0.0,
        soft_max=100.0
    )

    action: bpy.props.EnumProperty(
        name="Action",
        description="Bereinigungsart",
        items=[
            ('SELECT', "Select", "Markiert fehlerhafte Tracks"),
            ('DELETE_TRACK', "Delete Track", "Löscht fehlerhafte Tracks"),
            ('DELETE_SEGMENTS', "Delete Segments", "Löscht fehlerhafte Segmente"),
        ],
        default='DELETE_TRACK'
    )

    def execute(self, context: Context):
        # --- Gültigen Clip Editor finden ---
        override = None
        clip = None
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'CLIP_EDITOR':
                    space = area.spaces.active
                    if space and space.clip:
                        clip = space.clip
                        override = {
                            'window': window,
                            'screen': window.screen,
                            'area': area,
                            'region': area.regions[-1],
                            'space_data': space,
                            'edit_movieclip': space.clip,
                        }
                        break
            if clip:
                break

        if not clip or not override:
            self.report({'ERROR'}, "Kein aktiver Movie Clip im Clip Editor gefunden.")
            return {'CANCELLED'}

        # --- Parameter setzen ---
        settings = clip.tracking.settings
        settings.clean_action = self.action
        settings.clean_error = self.threshold

        # --- Operator mit Keyword-Parametern korrekt ausführen ---
        try:
            bpy.ops.clip.clean_error(
                override,
                execution_context='EXEC_DEFAULT'
            )
        except Exception as e:
            self.report({'ERROR'}, f"Clean Error fehlgeschlagen: {e}")
            return {'CANCELLED'}

        self.report({'INFO'}, f"Clean Error erfolgreich ({self.action}, Threshold={self.threshold:.2f})")
        return {'FINISHED'}


def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_clean_error_operator)

def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_clean_error_operator)

if __name__ == "__main__":
    register()
