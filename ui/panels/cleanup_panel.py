import bpy


class TRACKING_PT_cleanup_tools(bpy.types.Panel):
    bl_label = "Cleanup Tools"
    bl_idname = "TRACKING_PT_cleanup_tools"
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'Tracking Tools'

    def draw(self, context):
        layout = self.layout
        layout.operator("clip.cleanup_tracks", text="Cleanup Tracks")

