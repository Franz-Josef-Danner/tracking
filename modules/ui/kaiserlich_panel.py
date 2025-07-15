"""Sidebar panel for Kaiserlich Tracksycle."""

import bpy

from ..operators.tracksycle_operator import KAISERLICH_OT_auto_track_cycle


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

        layout.operator(KAISERLICH_OT_auto_track_cycle.bl_idname,
                        text="Auto Track starten")
        layout.prop(scene, "min_marker_count")
        layout.prop(scene, "min_track_length")
        layout.prop(scene, "error_threshold")
        layout.prop(scene, "debug_output")

__all__ = ["KAISERLICH_PT_tracking_tools"]

