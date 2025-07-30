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

        # Proxy-Funktionen
        layout.operator("tracking.create_proxy")
        layout.operator("tracking.enable_proxy")
        layout.operator("tracking.disable_proxy")

        # Analyse & Tracking
        layout.operator("tracking.detect_features_once")
        layout.operator("tracking.track_bidirectional")
        layout.operator("tracking.select_short_tracks")

        # Berechnungen
        layout.operator("tracking.calculate_margin_distance")
        layout.operator("tracking.calculate_marker_target")

        # Einstellungen setzen
        layout.operator("tracking.set_tracking_defaults")

        # Cleanup
        layout.operator("tracking.cleanup_error_tracks")
        layout.operator("tracking.cleanup_tracks")

        # Optimierung
        layout.operator("tracking.optimize_tracking")


panel_classes = (
    TRACKING_PT_api_functions,
)
