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
        layout.operator('clip.optimized_test_cycle', text='Detail Track')


class CLIP_PT_test_panel(bpy.types.Panel):
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'Addon'
    bl_label = 'API Funktionen'

    def draw(self, context):
        layout = self.layout
        layout.operator('clip.all_detect', text='Cycle Detect')
        layout.operator('clip.api_defaults', text='Defaults')
        layout.operator('clip.proxy_on', text='Proxy on')
        layout.operator('clip.proxy_off', text='Proxy off')
        layout.operator('clip.track_bidirectional', text='Track')
        layout.operator('clip.track_partial', text='Track Partial')
        layout.operator('clip.count_button', text='Count')
        layout.operator('clip.prefix_new', text='Name New')
        layout.operator('clip.prefix_track', text='Name Track')
        layout.operator('clip.prefix_good', text='Name GOOD')
        layout.operator('clip.select_active_tracks', text='Select TRACK')
        layout.operator('clip.select_new_tracks', text='Select NEW')
        layout.operator('clip.delete_selected', text='Delete')
        layout.operator('clip.select_short_tracks', text='Select Short Tracks')
        layout.operator('clip.pattern_up', text='Pattern+')
        layout.operator('clip.pattern_down', text='Pattern-')
        layout.operator('clip.motion_cycle', text='Motion Model')
        layout.operator('clip.match_cycle', text='Match')
        layout.operator('clip.channel_r_on', text='Channel R on')
        layout.operator('clip.channel_r_off', text='Channel R off')
        layout.operator('clip.channel_b_on', text='Channel B on')
        layout.operator('clip.channel_b_off', text='Channel B off')
        layout.operator('clip.channel_g_on', text='Channel G on')
        layout.operator('clip.channel_g_off', text='Channel G off')
        layout.operator('clip.frame_jump_custom', text='Frame Jump')
        layout.operator('clip.low_marker_frame', text='Low Marker Frame')
        layout.operator('clip.marker_position', text='Marker Position')
        layout.operator('clip.good_marker_position', text='GOOD Marker Position')
        layout.operator('clip.camera_solve', text='Kamera solve')
        layout.operator('clip.track_cleanup', text='Select Error Tracks')


class CLIP_PT_test_subpanel(bpy.types.Panel):
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'Addon'
    bl_parent_id = 'CLIP_PT_test_panel'
    bl_label = 'Test'

    def draw(self, context):
        layout = self.layout
        layout.operator('clip.setup_defaults', text='Test Defaults')
        layout.operator('clip.defaults_detect', text='Test Detect Pattern')
        layout.operator('clip.motion_detect', text='Test Detect MM')
        layout.operator('clip.channel_detect', text='Test Detect CH')
        layout.operator('clip.apply_detect_settings', text='Test Detect Apply')
        layout.operator('clip.detect_button', text='Test Detect')
        layout.operator('clip.prefix_test', text='Name Test')
        layout.operator('clip.track_full', text='Track Test')
        layout.operator('clip.test_track_backwards', text='Test Track backwards')
        layout.operator('clip.test_button', text='Test')

panel_classes = (
    CLIP_PT_tracking_panel,
    CLIP_PT_final_panel,
    CLIP_PT_stufen_panel,
    CLIP_PT_test_panel,
    CLIP_PT_test_subpanel,
)

