"""Core operator for the Kaiserlich Tracksycle addon."""

import bpy


class KAISERLICH_OT_auto_track_cycle(bpy.types.Operator):
    """Start the automated tracking cycle"""

    bl_idname = "kaiserlich.auto_track_cycle"
    bl_label = "Auto Track Cycle"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        self.report({'INFO'}, "Auto track cycle started")
        # Placeholder for tracking logic
        return {'FINISHED'}


class KAISERLICH_PT_tracking_tools(bpy.types.Panel):
    """UI panel for the Kaiserlich Tracksycle addon."""

    bl_label = "Tracking Tools"
    bl_idname = "KAISERLICH_PT_tracking_tools"
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Kaiserlich"

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        layout.operator(KAISERLICH_OT_auto_track_cycle.bl_idname,
                        text="Auto Track")
        layout.prop(scene, "min_marker_count")
        layout.prop(scene, "min_track_length")
        layout.prop(scene, "error_threshold")
        layout.prop(scene, "debug_output")
