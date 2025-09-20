import bpy
from bpy.types import Operator

# Optionaler Direktimport für Fallback
try:
    from .bootstrap_O import CLIP_OT_bootstrap_cycle  # type: ignore
except Exception:
    CLIP_OT_bootstrap_cycle = None  # type: ignore

__all__ = ("CLIP_OT_camera_tracking_coordinator",)


class CLIP_OT_camera_tracking_coordinator(Operator):
    """Coordinator-Wrapper: löst Bootstrap aus (Tracker-Settings, Marker-Helper, Resets)."""

    bl_idname = "clip.camera_tracking_coordinator"
    bl_label = "Camera Tracking Coordinator (Bootstrap)"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        # 1) Bevor irgendetwas anderes passiert: Bootstrap-Operator auslösen
        try:
            # Normale Ausführung über die Operator-API (Klasse ist im Add-on registriert)
            bpy.ops.clip.bootstrap_cycle()
            self.report({'INFO'}, "Bootstrap ausgeführt (via bpy.ops)")
        except Exception as exc:
            # Fallback: direkt Klasse aufrufen (falls importierbar); bei Bedarf registrieren
            try:
                if CLIP_OT_bootstrap_cycle is not None:
                    try:
                        bpy.utils.register_class(CLIP_OT_bootstrap_cycle)
                    except Exception:
                        pass  # evtl. bereits registriert
                    op = CLIP_OT_bootstrap_cycle()
                    op.execute(context)
                    self.report({'INFO'}, "Bootstrap ausgeführt (direkter Fallback)")
                else:
                    self.report({'WARNING'}, f"Bootstrap konnte nicht über bpy.ops gestartet werden ({exc}) und Fallback ist nicht verfügbar.")
            except Exception as exc2:
                self.report({'WARNING'}, f"Bootstrap-Fallback fehlgeschlagen: {exc2}")
        # 2) Hier könnte optional weiterer Ablauf gestartet werden (z. B. Solve/Detect etc.)
        #    Vom Nutzer nicht gefordert – daher Ende nach Bootstrap.
        return {'FINISHED'}


def register():
    bpy.utils.register_class(CLIP_OT_camera_tracking_coordinator)


def unregister():
    try:
        bpy.utils.unregister_class(CLIP_OT_camera_tracking_coordinator)
    except Exception:
        pass