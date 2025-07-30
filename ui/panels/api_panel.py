import bpy


class TRACKING_PT_api_functions(bpy.types.Panel):
    bl_label = "API Funktionen"
    bl_idname = "TRACKING_PT_api_functions"
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Tracking Tools"

    def draw(self, context):
        layout = self.layout
        layout.label(text="Initialisierung:")
        layout.operator("tracking.set_tracking_defaults")
        layout.operator("tracking.create_proxy")
        layout.operator("tracking.enable_proxy")
        layout.operator("tracking.calculate_margin_distance")
        layout.operator("tracking.calculate_marker_target")

        layout.separator()
        layout.label(text="Markererkennung & Cleanup:")
        layout.operator("tracking.detect_features_once")
        layout.operator("tracking.select_short_tracks")
        layout.operator("tracking.cleanup_error_tracks")
        layout.operator("tracking.cleanup_tracks")

        layout.separator()
        layout.label(text="Tracking:")
        layout.operator("tracking.track_bidirectional")

        layout.separator()
        layout.label(text="Optimierung & Analyse:")
        layout.operator("tracking.optimize_tracking")
        layout.operator("tracking.find_next_low_marker_frame")
        layout.operator("tracking.set_playhead_to_frame")


panel_classes = (
    TRACKING_PT_api_functions,
)
