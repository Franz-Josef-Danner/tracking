from __future__ import annotations
import bpy

__all__ = ("CLIP_OT_tracking_coordinator", "register", "unregister")


class CLIP_OT_tracking_coordinator(bpy.types.Operator):
    bl_idname = "clip.tracking_coordinator"
    bl_label = "Tracking Orchestrator (Bootstrap)"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        return context.area and context.area.type == "CLIP_EDITOR"

    def invoke(self, context, event):
        # --- Bootstrap ---
        scn = context.scene
        scn["__detect_lock"] = False  # Lock zurücksetzen

        # Marker-Korridor berechnen
        try:
            from ..Helper.marker_helper_main import marker_helper_main
            ok, adapt, _ = marker_helper_main(context)
            self.report({'INFO'}, f"Marker Helper gestartet (adapt={adapt})")
        except Exception as ex:
            self.report({'WARNING'}, f"Marker Helper fehlgeschlagen: {ex}")

        # Tracker Defaults anwenden
        try:
            from ..Helper.tracker_settings import apply_tracker_settings
            apply_tracker_settings(context, log=True)
            self.report({'INFO'}, "Tracker Defaults gesetzt")
        except Exception as ex:
            self.report({'WARNING'}, f"Tracker Settings fehlgeschlagen: {ex}")

        return {'FINISHED'}


def register():
    bpy.utils.register_class(CLIP_OT_tracking_coordinator)


def unregister():
    bpy.utils.unregister_class(CLIP_OT_tracking_coordinator)
