import bpy
from bpy.types import Panel

class CLIP_PT_focal_control(Panel):
    bl_idname = "CLIP_PT_focal_control"
    bl_label = "Focal Control"
    bl_space_type = "CLIP_EDITOR"
    bl_region_type = "UI"
    bl_category = "Tracking"

    @classmethod
    def poll(cls, context):
        return getattr(getattr(context, "space_data", None), "type", "") == 'CLIP_EDITOR'

    def draw(self, context):
        layout = self.layout
        scn = context.scene

        layout.prop(scn, "tco_use_auto_focal", text="Auto-Brennweite (Refine)")
        col = layout.column()
        col.enabled = not bool(getattr(scn, "tco_use_auto_focal", True))
        col.prop(scn, "tco_focal_override", text="Fixe Brennweite (mm)")