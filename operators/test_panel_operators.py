import bpy


class TRACKING_OT_test_cycle(bpy.types.Operator):
    bl_idname = "tracking.test_cycle"
    bl_label = "Test Cycle"

    def execute(self, context):
        return {'FINISHED'}


class TRACKING_OT_test_base(bpy.types.Operator):
    bl_idname = "tracking.test_base"
    bl_label = "Test Base"

    def execute(self, context):
        return {'FINISHED'}


class TRACKING_OT_test_place_marker(bpy.types.Operator):
    bl_idname = "tracking.test_place_marker"
    bl_label = "Place Marker"

    def execute(self, context):
        return {'FINISHED'}


class TRACKING_OT_test_track_markers(bpy.types.Operator):
    bl_idname = "tracking.test_track_markers"
    bl_label = "Track Markers"

    def execute(self, context):
        return {'FINISHED'}


class TRACKING_OT_test_error_value(bpy.types.Operator):
    bl_idname = "tracking.test_error_value"
    bl_label = "Error Value"

    def execute(self, context):
        return {'FINISHED'}


class TRACKING_OT_test_tracking_lengths(bpy.types.Operator):
    bl_idname = "tracking.test_tracking_lengths"
    bl_label = "Tracking Lengths"

    def execute(self, context):
        return {'FINISHED'}


class TRACKING_OT_test_cycle_motion(bpy.types.Operator):
    bl_idname = "tracking.test_cycle_motion"
    bl_label = "Cycle Motion"

    def execute(self, context):
        return {'FINISHED'}


class TRACKING_OT_test_tracking_channels(bpy.types.Operator):
    bl_idname = "tracking.test_tracking_channels"
    bl_label = "Tracking Channels"

    def execute(self, context):
        return {'FINISHED'}


operator_classes = (
    TRACKING_OT_test_cycle,
    TRACKING_OT_test_base,
    TRACKING_OT_test_place_marker,
    TRACKING_OT_test_track_markers,
    TRACKING_OT_test_error_value,
    TRACKING_OT_test_tracking_lengths,
    TRACKING_OT_test_cycle_motion,
    TRACKING_OT_test_tracking_channels,
)
