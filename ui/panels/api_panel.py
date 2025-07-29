import bpy


class TRACKING_PT_api_functions(bpy.types.Panel):
    bl_label = "API Funktionen"
    bl_idname = "TRACKING_PT_api_functions"
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Tracking Tools"

    def draw(self, context):
        layout = self.layout
        layout.label(text="Tracking-Schritte manuell ausführen:")
        layout.operator("tracking.create_proxy")
        layout.operator("tracking.detect_features_once")
        layout.operator("tracking.track_bidirectional")
        layout.operator("tracking.select_short_tracks")
        layout.operator("tracking.cleanup_error_tracks")
        layout.operator("tracking.cleanup_tracks")
        layout.operator("tracking.optimize_tracking")


panel_classes = (
    TRACKING_PT_api_functions,
)
