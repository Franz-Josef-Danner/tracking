import bpy

from ..helpers.feature_detection import detect_features_once
from ..helpers.tracking_variants import track_bidirectional
from ..helpers.select_short_tracks import select_short_tracks
from .cleanup_tracks import cleanup_error_tracks
from ..helpers.optimize_tracking import optimize_tracking_parameters


def create_proxy():
    """Build proxies using the existing operator if available."""
    if bpy.ops.clip.proxy_build.poll():
        bpy.ops.clip.proxy_build()


def cleanup_tracks():
    """Run the cleanup operator if available."""
    if bpy.ops.clip.cleanup.poll():
        bpy.ops.clip.cleanup()


class TRACKING_OT_create_proxy(bpy.types.Operator):
    bl_idname = "tracking.create_proxy"
    bl_label = "Create Proxy"

    def execute(self, context):
        create_proxy()
        return {'FINISHED'}


class TRACKING_OT_detect_features_once(bpy.types.Operator):
    bl_idname = "tracking.detect_features_once"
    bl_label = "Detect Features"

    def execute(self, context):
        detect_features_once()
        return {'FINISHED'}


class TRACKING_OT_track_bidirectional(bpy.types.Operator):
    bl_idname = "tracking.track_bidirectional"
    bl_label = "Track Bidirectional"

    def execute(self, context):
        scene = context.scene
        track_bidirectional(scene.frame_start, scene.frame_end)
        return {'FINISHED'}


class TRACKING_OT_select_short_tracks(bpy.types.Operator):
    bl_idname = "tracking.select_short_tracks"
    bl_label = "Select Short Tracks"

    def execute(self, context):
        clip = getattr(context.space_data, "clip", None)
        if clip is None:
            self.report({'WARNING'}, "Kein aktiver Movie Clip gefunden.")
            return {'CANCELLED'}
        select_short_tracks(clip, context.scene.frames_track)
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
        return {'FINISHED'}


class TRACKING_OT_cleanup_tracks(bpy.types.Operator):
    bl_idname = "tracking.cleanup_tracks"
    bl_label = "Cleanup Tracks"

    def execute(self, context):
        cleanup_tracks()
        return {'FINISHED'}


class TRACKING_OT_optimize_tracking(bpy.types.Operator):
    bl_idname = "tracking.optimize_tracking"
    bl_label = "Optimize Tracking"

    def execute(self, context):
        optimize_tracking_parameters()
        return {'FINISHED'}


operator_classes = (
    TRACKING_OT_create_proxy,
    TRACKING_OT_detect_features_once,
    TRACKING_OT_track_bidirectional,
    TRACKING_OT_select_short_tracks,
    TRACKING_OT_cleanup_error_tracks,
    TRACKING_OT_cleanup_tracks,
    TRACKING_OT_optimize_tracking,
)
