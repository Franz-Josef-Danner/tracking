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
        # --- Clip Editor und Clip finden ---
        clip = None
        override = None

        for window in bpy.context.window_manager.windows:
            screen = window.screen
            for area in screen.areas:
                if area.type == 'CLIP_EDITOR':
                    space = area.spaces.active
                    if space and space.clip:
                        clip = space.clip
                        region = None
                        for r in area.regions:
                            if r.type == 'WINDOW':
                                region = r
                                break
                        override = {
                            "window": window,
                            "screen": screen,
                            "area": area,
                            "region": region,
                            "space_data": space,
                            "edit_movieclip": clip,
                        }
                        break
            if clip:
                break

        if not clip or not override:
            self.report({'ERROR'}, "Kein aktiver Clip im Clip-Editor gefunden.")
            return {'CANCELLED'}

        # --- Einstellungen setzen ---
        settings = clip.tracking.settings
        settings.clean_action = self.action
        settings.clean_error = self.threshold

        # --- Sicheren Aufruf ausführen ---
        try:
            bpy.ops.clip.clean_error(
                override,
                'EXEC_DEFAULT'  # hier KEIN weiteres keyword argument!
            )
        except TypeError:
            # Alternative Syntax für Blender 4.4 (sicher)
            bpy.ops.clip.clean_error(
                override
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
