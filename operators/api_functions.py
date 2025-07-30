import bpy

from ..helpers.proxy_utils import create_proxy, enable_proxy, disable_proxy
from ..helpers.feature_detection import detect_features_once
from ..helpers.tracking_variants import track_bidirectional
from ..helpers.select_short_tracks import select_short_tracks
from ..operators.cleanup_tracks import cleanup_error_tracks
from ..helpers.optimize_tracking import optimize_tracking_parameters
from ..helpers.clip_resolution import calculate_base_values_from_clip
from ..helpers.marker_validation import calculate_marker_target_from_ui
from ..helpers.tracking_defaults import set_default_tracking_settings


def cleanup_tracks():
    """Run the cleanup operator if available."""
    if bpy.ops.clip.cleanup.poll():
        bpy.ops.clip.cleanup()


class TRACKING_OT_create_proxy(bpy.types.Operator):
    bl_idname = "tracking.create_proxy"
    bl_label = "Create Proxy"

    def execute(self, context):
        create_proxy()
        self.report({'INFO'}, "Proxy erstellt")
        return {'FINISHED'}


class TRACKING_OT_enable_proxy(bpy.types.Operator):
    bl_idname = "tracking.enable_proxy"
    bl_label = "Enable Proxy"

    def execute(self, context):
        enable_proxy()
        self.report({'INFO'}, "Proxy aktiviert")
        return {'FINISHED'}


class TRACKING_OT_disable_proxy(bpy.types.Operator):
    bl_idname = "tracking.disable_proxy"
    bl_label = "Disable Proxy"

    def execute(self, context):
        disable_proxy()
        self.report({'INFO'}, "Proxy deaktiviert")
        return {'FINISHED'}


class TRACKING_OT_detect_features_once(bpy.types.Operator):
    bl_idname = "tracking.detect_features_once"
    bl_label = "Detect Features"

    def execute(self, context):
        detect_features_once()
        self.report({'INFO'}, "Features erkannt")
        return {'FINISHED'}


class TRACKING_OT_track_bidirectional(bpy.types.Operator):
    bl_idname = "tracking.track_bidirectional"
    bl_label = "Track Bidirectional"

    def execute(self, context):
        scene = context.scene
        track_bidirectional(scene.frame_start, scene.frame_end)
        self.report({'INFO'}, "Tracking abgeschlossen")
        return {'FINISHED'}


class TRACKING_OT_select_short_tracks(bpy.types.Operator):
    bl_idname = "tracking.select_short_tracks"
    bl_label = "Select Short Tracks"

    def execute(self, context):
        clip = getattr(context.space_data, "clip", None)
        if clip is None:
            self.report({'WARNING'}, "Kein aktiver Movie Clip gefunden.")
            return {'CANCELLED'}
        count = select_short_tracks(clip, context.scene.frames_track)
        self.report({'INFO'}, f"{count} kurze Tracks ausgewählt")
        return {'FINISHED'}


class TRACKING_OT_calculate_margin_distance(bpy.types.Operator):
    bl_idname = "tracking.calculate_margin_distance"
    bl_label = "Berechne Margin & Distance"

    def execute(self, context):
        margin, distance = calculate_base_values_from_clip(context=context)
        self.report({'INFO'}, f"Margin: {margin}, MinDist: {distance}")
        return {'FINISHED'}


class TRACKING_OT_calculate_marker_target(bpy.types.Operator):
    bl_idname = "tracking.calculate_marker_target"
    bl_label = "Markerziel berechnen"

    def execute(self, context):
        target = calculate_marker_target_from_ui(context=context)
        self.report({'INFO'}, f"Markerziel: {target}")
        return {'FINISHED'}


class TRACKING_OT_set_tracking_defaults(bpy.types.Operator):
    bl_idname = "tracking.set_tracking_defaults"
    bl_label = "Tracking-Defaults"

    def execute(self, context):
        set_default_tracking_settings(context=context)
        self.report({'INFO'}, "Tracking-Defaults gesetzt")
        return {'FINISHED'}


class TRACKING_OT_cleanup_error_tracks(bpy.types.Operator):
    bl_idname = "tracking.cleanup_error_tracks"
    bl_label = "Cleanup Error Tracks"

    def execute(self, context):
        clip = getattr(context.space_data, "clip", None)
        if clip is None:
            self.report({'WARNING'}, "Kein aktiver Movie Clip gefunden.")
            return {'CANCELLED'}
        cleanup_error_tracks(context.scene, clip)
        self.report({'INFO'}, "Fehlerhafte Tracks bereinigt")
        return {'FINISHED'}


class TRACKING_OT_cleanup_tracks(bpy.types.Operator):
    bl_idname = "tracking.cleanup_tracks"
    bl_label = "Cleanup Tracks"

    def execute(self, context):
        cleanup_tracks()
        self.report({'INFO'}, "Tracks bereinigt")
        return {'FINISHED'}


class TRACKING_OT_optimize_tracking(bpy.types.Operator):
    bl_idname = "tracking.optimize_tracking"
    bl_label = "Optimize Tracking"

    def execute(self, context):
        optimize_tracking_parameters()
        self.report({'INFO'}, "Optimierung abgeschlossen")
        return {'FINISHED'}


operator_classes = (
    TRACKING_OT_create_proxy,
    TRACKING_OT_enable_proxy,
    TRACKING_OT_disable_proxy,
    TRACKING_OT_detect_features_once,
    TRACKING_OT_track_bidirectional,
    TRACKING_OT_select_short_tracks,
    TRACKING_OT_calculate_margin_distance,
    TRACKING_OT_calculate_marker_target,
    TRACKING_OT_set_tracking_defaults,
    TRACKING_OT_cleanup_error_tracks,
    TRACKING_OT_cleanup_tracks,
    TRACKING_OT_optimize_tracking,
)
