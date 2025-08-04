import bpy


class TRACKING_PT_api_functions(bpy.types.Panel):
    bl_label = "Tracking"
    bl_idname = "TRACKING_PT_api_functions"
    bl_space_type = "CLIP_EDITOR"
    bl_region_type = "UI"
    bl_category = "Tracking Tools"

    def draw(self, context):
        layout = self.layout
        layout.operator("tracking.bidirectional_tracking", text="Track")
