import bpy

from ..helpers import (
    run_tracking_optimization,
    track_markers_until_end,
    get_tracking_lengths,
    cycle_motion_model,
    set_tracking_channels,
)
from ..helpers.test_cyclus import error_value


class TRACKING_OT_test_cycle(bpy.types.Operator):
    bl_idname = "tracking.test_cycle"
    bl_label = "Test Cycle"

    def execute(self, context):
        result = run_tracking_optimization(context)
        self.report(
            {'INFO'},
            f"pattern={result.get('pattern')} motion={result.get('motion')} channels={result.get('channels')}"
        )
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
        track_markers_until_end()
        self.report({'INFO'}, "Tracking gestartet")
        return {'FINISHED'}


class TRACKING_OT_test_error_value(bpy.types.Operator):
    bl_idname = "tracking.test_error_value"
    bl_label = "Error Value"

    def execute(self, context):
        value = error_value(context)
        self.report({'INFO'}, f"Error: {value:.4f}")
        return {'FINISHED'}


class TRACKING_OT_test_tracking_lengths(bpy.types.Operator):
    bl_idname = "tracking.test_tracking_lengths"
    bl_label = "Tracking Lengths"

    def execute(self, context):
        lengths = get_tracking_lengths()
        if not lengths:
            self.report({'WARNING'}, "Keine Tracks ausgewählt")
        else:
            for name, data in lengths.items():
                print(f"{name}: {data['length']} Frames")
            self.report({'INFO'}, "Längen ausgegeben")
        return {'FINISHED'}


class TRACKING_OT_test_cycle_motion(bpy.types.Operator):
    bl_idname = "tracking.test_cycle_motion"
    bl_label = "Cycle Motion"

    def execute(self, context):
        # Der eigentliche Wechsel wird vom Operator TRACKING_OT_cycle_motion_model erledigt
        self.report({'INFO'}, "Motion Model gewechselt")
        return {'FINISHED'}


class TRACKING_OT_test_tracking_channels(bpy.types.Operator):
    bl_idname = "tracking.test_tracking_channels"
    bl_label = "Tracking Channels"

    def execute(self, context):
        set_tracking_channels()
        self.report({'INFO'}, "Tracking-Kanäle gesetzt")
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
