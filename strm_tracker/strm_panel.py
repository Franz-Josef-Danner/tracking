import bpy


class STRM_PT_Panel(bpy.types.Panel):
    bl_label = "STRM Tracker"
    bl_idname = "CLIP_PT_strm_tracker"
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'STRM'

    def draw(self, context):
        layout = self.layout
        layout.operator("clip.strm_analyze", icon='VIEWZOOM')
        layout.operator("clip.strm_toggle_overlay", icon='GRID')
