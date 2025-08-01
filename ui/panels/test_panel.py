import bpy


class TRACKING_PT_test(bpy.types.Panel):
    bl_label = "Test"
    bl_idname = "TRACKING_PT_test"
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Tracking Tools"
    bl_parent_id = "TRACKING_PT_api_functions"

    def draw(self, context):
        layout = self.layout
        layout.operator("tracking.test_cycle", text="Test Cycle")


class TRACKING_PT_test_details(bpy.types.Panel):
    bl_label = "Test details"
    bl_idname = "TRACKING_PT_test_details"
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Tracking Tools"
    bl_parent_id = "TRACKING_PT_test"

    def draw(self, context):
        layout = self.layout
        layout.operator('tracking.test_marker_base')
        layout.operator("tracking.place_marker", text="Place Marker")
        layout.operator("tracking.test_track_markers", text="Track Markers")
        layout.operator("tracking.test_error_value", text="Error Value")
        layout.operator("tracking.test_tracking_lengths", text="Tracking Lengths")
        layout.operator("tracking.test_cycle_motion", text="Cycle Motion")
        layout.operator("tracking.test_tracking_channels", text="Tracking Channels")


panel_classes = (
    TRACKING_PT_test,
    TRACKING_PT_test_details,
)
