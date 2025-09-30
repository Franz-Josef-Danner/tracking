import bpy

class TRACKING_PT_tools_panel(bpy.types.Panel):
    bl_label = "Tracking Tools"
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'Tracking'

    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)
        col.operator('tracking.detect_markers', text='Detect Markers', icon='TRACKING')
