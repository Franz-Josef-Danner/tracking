import bpy


class TRACKING_PT_api_functions(bpy.types.Panel):
    bl_label = "API Funktionen"
    bl_idname = "TRACKING_PT_api_functions"
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Tracking Tools"

    def draw(self, context):
        layout = self.layout
        layout.prop(context.scene, 'marker_basis', text='Marker/Frame')
        layout.prop(context.scene, 'frames_per_track', text='Frames/Track')
        layout.prop(context.scene, 'error_per_track', text='Error/Track')
        layout.operator('tracking.marker_basis_values')
        layout.operator('tracking.place_marker')
        layout.operator('tracking.bidirectional_tracking')
        layout.operator("clip.cleanup_tracks", text="Cleanup Tracks")
