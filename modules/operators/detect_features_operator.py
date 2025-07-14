"""Operator wrapper for feature detection."""

from __future__ import annotations

import bpy
from bpy.props import FloatProperty

from ..detection.detect_no_proxy import detect_features_no_proxy
from ..util.tracker_logger import TrackerLogger, configure_logger


class KAISERLICH_OT_detect_features(bpy.types.Operator):  # type: ignore[misc]
    """Detect features on the active movie clip."""

    bl_idname = "kaiserlich.detect_features"
    bl_label = "Detect Features"
    bl_options = {'REGISTER', 'UNDO'}

    threshold: FloatProperty(
        name="Threshold",
        description="Detection threshold",
        default=1.0,
        min=0.0,
    )
    margin: FloatProperty(
        name="Margin",
        description="Margin around detected features (0 = auto)",
        default=0.0,
        min=0.0,
    )
    distance: FloatProperty(
        name="Distance",
        description="Minimum distance between features (0 = auto)",
        default=0.0,
        min=0.0,
    )

    def execute(self, context):  # type: ignore[override]
        space = context.space_data
        clip = getattr(space, "clip", None)
        if not clip:
            self.report({'ERROR'}, "No clip loaded")
            return {'CANCELLED'}

        scene = context.scene
        configure_logger(debug=getattr(scene, "debug_output", False))
        logger = TrackerLogger()

        detect_features_no_proxy(
            clip,
            threshold=self.threshold,
            margin=self.margin or None,
            distance=self.distance or None,
            logger=logger,
        )
        return {'FINISHED'}


__all__ = ["KAISERLICH_OT_detect_features"]
