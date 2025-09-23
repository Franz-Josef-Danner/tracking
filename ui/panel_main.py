import bpy
from bpy.types import Panel

class CLIP_PT_kaiserlich_panel(Panel):
    bl_space_type = "CLIP_EDITOR"
    bl_region_type = "UI"
    bl_category = "Kaiserlich"
    bl_label = "Kaiserlich Tracker"

    @classmethod
    def poll(cls, context):
        return getattr(getattr(context, "space_data", None), "type", "") == 'CLIP_EDITOR'

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        layout.label(text="Tracking Einstellungen")
        if hasattr(scene, "marker_frame"):
            layout.prop(scene, "marker_frame")
        if hasattr(scene, "frames_track"):
            layout.prop(scene, "frames_track")
        if hasattr(scene, "error_track"):
            layout.prop(scene, "error_track")

        layout.separator()

        # Focal-Steuerung im selben Panel über dem Start-Button
        layout.prop(scene, "tco_use_auto_focal", text="Auto-Brennweite (Refine)")
        col = layout.column()
        col.enabled = not bool(getattr(scene, "tco_use_auto_focal", True))
        col.prop(scene, "tco_focal_override", text="Fixe Brennweite (mm)")

        layout.separator()
        layout.operator("clip.kaiserlich_coordinator_launcher", text="Coordinator starten")