"""
User Interface for the Kaiserlich Tracker add‑on.

This panel exposes controls for running detection/tracking cycles,
adjusting motion‑model thresholds and invoking the auto calibration
operator.  The layout broadly follows the upstream UI but adds an
additional button to start the automatic threshold calibration.
"""

from __future__ import annotations

import bpy


class KAISERLICHTRACKER_PT_panel(bpy.types.Panel):
    """UI panel displayed in the Movie Clip Editor sidebar."""

    bl_label = "Kaiserlich Tracker"
    bl_idname = "KAISERLICH_TRACKER_PT_panel"
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'Kaiserlich Tracker'

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return context.space_data and getattr(context.space_data, 'clip', None) is not None

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        scene = context.scene

        # Hauptbereich: Anzahl der Marker pro Frame, Cycle‑Buttons
        col = layout.column(align=True)
        if hasattr(scene, "kaiserlich_markers_per_frame"):
            col.prop(scene, "kaiserlich_markers_per_frame", text="Marker per Frame")
        col.operator("kaiserlich_tracker.detect_cycle", text="Detect Cyclus")
        col.operator("kaiserlich_tracker.track_cycle", text="Track Cycle")
        col.operator("kaiserlich_tracker.auto_calibrate", text="Auto-Calibrate Thresholds")

        layout.separator()

        # Rotation Thresholds
        layout.label(text="Rotation Thresholds")
        col = layout.column(align=True)
        col.prop(scene, "kaiserlich_rot_thresh_x", text="ΔX-Threshold")
        col.prop(scene, "kaiserlich_rot_thresh_y", text="ΔY-Threshold")

        layout.separator()
        # Scale Thresholds
        layout.label(text="Scale Thresholds")
        col = layout.column(align=True)
        col.prop(scene, "kaiserlich_scale_thresh_min", text="Min Scale Δ")
        col.prop(scene, "kaiserlich_scale_thresh_max", text="Max Scale Δ")

        layout.separator()
        # LocRotScale Thresholds
        layout.label(text="LocRotScale Thresholds")
        col = layout.column(align=True)
        col.prop(scene, "kaiserlich_rot_scale_thresh_rot", text="Rot+Scale ΔRot")
        col.prop(scene, "kaiserlich_rot_scale_thresh_scale", text="Rot+Scale ΔScale")

        layout.separator()
        # Perspective Threshold
        layout.label(text="Perspective Threshold")
        col = layout.column(align=True)
        col.prop(scene, "kaiserlich_perspective_thresh", text="Perspective Δ")


def register():
    bpy.utils.register_class(KAISERLICHTRACKER_PT_panel)
    # Register scene properties if not already present
    scn = bpy.types.Scene
    # Rotation thresholds
    if not hasattr(scn, "kaiserlich_rot_thresh_x"):
        scn.kaiserlich_rot_thresh_x = bpy.props.FloatProperty(
            name="ΔX Threshold",
            description="Minimaler ΔX-Unterschied zur Erkennung von Rotation",
            default=0.001,
            min=0.0,
            soft_max=0.01,
            precision=6,
            subtype='FACTOR',
        )
    if not hasattr(scn, "kaiserlich_rot_thresh_y"):
        scn.kaiserlich_rot_thresh_y = bpy.props.FloatProperty(
            name="ΔY Threshold",
            description="Minimaler ΔY-Unterschied zur Erkennung von Rotation",
            default=0.001,
            min=0.0,
            soft_max=0.01,
            precision=6,
            subtype='FACTOR',
        )
    # Scale thresholds
    if not hasattr(scn, "kaiserlich_scale_thresh_min"):
        scn.kaiserlich_scale_thresh_min = bpy.props.FloatProperty(
            name="Min Scale Δ",
            description="Minimale Abstandsänderung zur Erkennung von Skalierung",
            default=0.002,
            min=0.0,
            soft_max=0.02,
            precision=6,
            subtype='FACTOR',
        )
    if not hasattr(scn, "kaiserlich_scale_thresh_max"):
        scn.kaiserlich_scale_thresh_max = bpy.props.FloatProperty(
            name="Max Scale Δ",
            description="Maximale Abstandsänderung, bevor Skalierung als instabil gilt",
            default=0.010,
            min=0.0,
            soft_max=0.05,
            precision=6,
            subtype='FACTOR',
        )
    # LocRotScale thresholds
    if not hasattr(scn, "kaiserlich_rot_scale_thresh_rot"):
        scn.kaiserlich_rot_scale_thresh_rot = bpy.props.FloatProperty(
            name="Rot+Scale ΔRot",
            description="Empfindlichkeit für kombinierte Rotation und Skalierung (Rotationsteil)",
            default=0.002,
            min=0.0,
            soft_max=0.02,
            precision=6,
            subtype='FACTOR',
        )
    if not hasattr(scn, "kaiserlich_rot_scale_thresh_scale"):
        scn.kaiserlich_rot_scale_thresh_scale = bpy.props.FloatProperty(
            name="Rot+Scale ΔScale",
            description="Empfindlichkeit für kombinierte Rotation und Skalierung (Skalierungsteil)",
            default=0.005,
            min=0.0,
            soft_max=0.02,
            precision=6,
            subtype='FACTOR',
        )
    # Perspective threshold
    if not hasattr(scn, "kaiserlich_perspective_thresh"):
        scn.kaiserlich_perspective_thresh = bpy.props.FloatProperty(
            name="Perspective Δ",
            description="Empfindlichkeit für perspektivische Abweichung (Tiefe/Parallaxe)",
            default=0.002,
            min=0.0,
            soft_max=0.02,
            precision=6,
            subtype='FACTOR',
        )


def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_PT_panel)
    scn = bpy.types.Scene
    for prop in (
        "kaiserlich_rot_thresh_x",
        "kaiserlich_rot_thresh_y",
        "kaiserlich_scale_thresh_min",
        "kaiserlich_scale_thresh_max",
        "kaiserlich_rot_scale_thresh_rot",
        "kaiserlich_rot_scale_thresh_scale",
        "kaiserlich_perspective_thresh",
    ):
        if hasattr(scn, prop):
            delattr(scn, prop)
