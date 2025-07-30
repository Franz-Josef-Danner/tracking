import bpy

class CLIP_PT_final_panel(bpy.types.Panel):
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'Addon'
    bl_label = 'Final'

    def draw(self, context):
        layout = self.layout
        layout.prop(context.scene, 'marker_frame', text='Marker/Frame')
        layout.prop(context.scene, 'frames_track', text='Frames/Track')
        layout.prop(context.scene, 'error_threshold', text='Error Threshold')


class CLIP_PT_stufen_panel(bpy.types.Panel):
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'Addon'
    bl_label = 'Stufen'

    def draw(self, context):
        layout = self.layout
        layout.operator('clip.proxy_build', text='Proxy erstellen (50%)')
        layout.operator('clip.track_nr1', text='Track Nr. 1')
        layout.operator('clip.cleanup', text='Cleanup')
        layout.operator('clip.cleanup_operator', text='Cleanup Tracks')
        layout.operator('clip.track_nr2', text='Track Nr. 2')


panel_classes = (
    CLIP_PT_final_panel,
    CLIP_PT_stufen_panel,
)
