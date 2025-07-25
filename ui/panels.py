import bpy

class CLIP_PT_tracking_panel(bpy.types.Panel):
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'Track'
    bl_label = 'Addon Panel'

    def draw(self, context):
        layout = self.layout
        layout.label(text="Addon Informationen")


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
        layout.operator('clip.panel_button', text='Proxy')
        layout.operator('clip.track_nr1', text='Track Nr. 1')
        layout.operator('clip.cleanup', text='Cleanup')


class CLIP_PT_test_panel(bpy.types.Panel):
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'Addon'
    bl_label = 'API Funktionen'

    def draw(self, context):
        layout = self.layout
        # Intentionally left empty to reset the panel
        layout.label(text="Keine Aktionen verf\xfcgbar")


class CLIP_PT_test_subpanel(bpy.types.Panel):
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'Addon'
    bl_parent_id = 'CLIP_PT_test_panel'
    bl_label = 'Test'

    def draw(self, context):
        layout = self.layout
        layout.operator('clip.prefix_test_name', text='TEST Name')

panel_classes = (
    CLIP_PT_tracking_panel,
    CLIP_PT_final_panel,
    CLIP_PT_stufen_panel,
    CLIP_PT_test_panel,
    CLIP_PT_test_subpanel,
)

