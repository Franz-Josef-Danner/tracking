"""Detect features with dynamic threshold adjustment."""

import bpy
from bpy.types import Operator
from bpy.props import IntProperty, FloatProperty


class KAISERLICH_OT_detect_features(Operator):
    """Detects features iteratively adjusting the threshold."""

    bl_idname = "kaiserlich.detect_features"
    bl_label = "Detect Features"
    bl_options = {"REGISTER", "UNDO"}

    min_marker_count: IntProperty(
        name="Minimum Marker Count",
        default=10,
        min=1,
        description="Minimum markers expected after detection",
    )
    threshold_start: FloatProperty(
        name="Initial Threshold",
        default=1.0,
        min=0.0001,
        description="Starting threshold for detection",
    )
    max_attempts: IntProperty(
        name="Max Attempts",
        default=10,
        min=1,
        description="Maximum detection iterations",
    )
    distance_factor: FloatProperty(
        name="Distance Factor",
        default=20.0,
        min=1.0,
        description="Distance parameter factor relative to clip width",
    )
    margin_factor: FloatProperty(
        name="Margin Factor",
        default=200.0,
        min=1.0,
        description="Margin parameter factor relative to clip width",
    )

    def execute(self, context):
        clip = context.space_data.clip
        if not clip:
            self.report({'ERROR'}, "No active clip")
            return {'CANCELLED'}

        width = clip.size[0]
        threshold = self.threshold_start
        attempts = 0

        clip.proxy.build_50 = False
        clip.use_proxy = False

        pattern_size = min(max(int(width / 100), 1), 100)
        settings = clip.tracking.settings
        settings.default_pattern_size = pattern_size

        while attempts < self.max_attempts:
            bpy.ops.clip.detect_features(
                threshold=threshold,
                margin=width / self.margin_factor,
                distance=width / self.distance_factor,
            )

            marker_count = len(clip.tracking.tracks)
            if marker_count >= self.min_marker_count:
                break

            expected = self.min_marker_count * 4
            threshold = max(threshold * ((marker_count + 0.1) / expected), 0.0001)
            threshold = round(threshold, 5)
            attempts += 1

        return {'FINISHED'}
