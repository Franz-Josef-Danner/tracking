"""Sidebar panel for Kaiserlich Tracksycle."""

import bpy

from ..operators.tracksycle_operator import KAISERLICH_OT_auto_track_cycle
from ..operators.cleanup_new_tracks_operator import (
    KAISERLICH_OT_cleanup_new_tracks,
)
from ..operators.detect_features_operator import KAISERLICH_OT_detect_features
from ..operators.tracking_marker_operator import KAISERLICH_OT_tracking_marker
from ..operators.combine_actions_operator import KAISERLICH_OT_run_all_except_proxy


class KAISERLICH_PT_tracking_tools(bpy.types.Panel):
    """UI panel hosting the main operator and settings."""

    bl_label = "Kaiserlich"
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Kaiserlich"

    @classmethod
    def poll(cls, context):
        space = context.space_data
        return space and space.type == 'CLIP_EDITOR' and space.clip is not None

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        layout.operator(
            KAISERLICH_OT_auto_track_cycle.bl_idname, text="Auto Track starten"
        )
        layout.operator(
            KAISERLICH_OT_detect_features.bl_idname, text="Detect Features"
        )
        layout.operator(
            KAISERLICH_OT_tracking_marker.bl_idname, text="Tracking Marker"
        )
        layout.operator(
            KAISERLICH_OT_run_all_except_proxy.bl_idname,
            text="Alles außer Proxy",
        )
        layout.prop(scene, "min_marker_count")
        layout.prop(scene, "min_track_length")
        layout.prop(scene, "error_threshold")
        layout.prop(scene, "debug_output")


class KAISERLICH_PT_cleanup_tools(bpy.types.Panel):
    """UI panel hosting cleanup utilities."""

    bl_label = "Kaiserlich Cleanup"
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Kaiserlich"

    @classmethod
    def poll(cls, context):
        space = context.space_data
        return space and space.type == 'CLIP_EDITOR' and space.clip is not None

    def draw(self, context):
        layout = self.layout

        layout.operator(
            KAISERLICH_OT_cleanup_new_tracks.bl_idname, text="Cleanup NEW Tracks"
        )

__all__ = [
    "KAISERLICH_PT_tracking_tools",
    "KAISERLICH_PT_cleanup_tools",
]

