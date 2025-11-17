# UI/ui.py
import bpy

class KAISERLICHTRACKER_PT_panel(bpy.types.Panel):
    bl_label = "Kaiserlich Tracker"
    bl_idname = "KAISERLICH_TRACKER_PT_panel"
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'Kaiserlich Tracker'

    @classmethod
    def poll(cls, context):
        return context.space_data and context.space_data.clip is not None

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        # Property layout: Label on the left, field on the right – without dark box background
        col = layout.column(align=True)
        col.use_property_split = True
        col.use_property_decorate = False
        col.prop(scene, "kaiserlich_markers_per_frame", text="Markers per Frame")
        col.prop(scene, "kaiserlich_frames_per_track", text="Frames per Track")
        col.prop(scene, "max_error_value", text="Max Error Value")

        # ▶️ Buttons
        col = layout.column(align=True)
        col.operator("kaiserlich_tracker.master_operator", text="master", icon="SYSTEM")
        col = layout.column(align=True)

        col.operator("kaiserlichtracker.master_deep_test_operator", text="motion model test", icon="ZOOM_IN")
        col.operator("kaiserlich_tracker.master_detect_adapt", text="detect features", icon="STICKY_UVS_DISABLE")
        col = layout.column(align=True)

        row = col.row(align=True)
        row.operator("kaiserlich_tracker.master_track_cycle_backwards", text="track", icon="TRACKING_BACKWARDS")
        row.operator("kaiserlich_tracker.master_track_cycle", text="track", icon="TRACKING_FORWARDS")

        col = layout.column(align=True)
        col.operator("kaiserlich_tracker.master_resolve_operator", text="camera solve", icon="OUTLINER_OB_CAMERA")
        col.operator("kaiserlich_tracker.clean_error_operator", text="error cleanup", icon="ERROR")
      
        layout.separator()

        # --- Rotation Thresholds ---
        layout.label(text="Rotation Thresholds")
        col = layout.column(align=True)
        col.use_property_split = True
        col.use_property_decorate = False
        col.prop(scene, "kaiserlich_rot_thresh_x", text="ΔX Threshold")
        col.prop(scene, "kaiserlich_rot_thresh_y", text="ΔY Threshold")

        layout.separator()

        # --- Scale Thresholds ---
        layout.label(text="Scale Thresholds")
        col = layout.column(align=True)
        col.use_property_split = True
        col.use_property_decorate = False
        col.prop(scene, "kaiserlich_scale_thresh_min", text="Min Scale Δ")
        col.prop(scene, "kaiserlich_scale_thresh_max", text="Max Scale Δ")

        layout.separator()

        # --- LocRotScale Thresholds ---
        layout.label(text="LocRotScale Thresholds")
        col = layout.column(align=True)
        col.use_property_split = True
        col.use_property_decorate = False
        col.prop(scene, "kaiserlich_rot_scale_thresh_rot", text="Rot+Scale ΔRot")
        col.prop(scene, "kaiserlich_rot_scale_thresh_scale", text="Rot+Scale ΔScale")

        layout.separator()

        # --- Perspective Thresholds ---
        layout.label(text="Perspective Thresholds")
        col = layout.column(align=True)
        col.use_property_split = True
        col.use_property_decorate = False
        col.prop(scene, "kaiserlich_perspective_thresh", text="Perspective Δ")

        layout.separator()
        layout.label(text="Status")
        # Progress indicators with property binding
        layout.prop(scene, "kaiserlich_progress_title", text="Single Tests")
        layout.prop(scene, "kaiserlich_progress_step", text="Complete Test")
        layout.prop(scene, "kaiserlich_quality_percent", text="Track Quality")
        layout.prop(scene, "kaiserlich_marker_progress", text="Track Progress")

# ==========================================================
# Registration of UI Properties
# ==========================================================

def register():
    bpy.types.Scene.kaiserlich_rot_thresh_x = bpy.props.FloatProperty(
        name="ΔX Threshold",
        description="Minimum ΔX difference required to detect rotation",
        default=0.5,
        min=0,
        max=2,
        subtype='FACTOR',
    )
    bpy.types.Scene.kaiserlich_rot_thresh_y = bpy.props.FloatProperty(
        name="ΔY Threshold",
        description="Minimum ΔY difference required to detect rotation",
        default=0.5,
        min=0,
        max=2,
        subtype='FACTOR',
    )
    bpy.types.Scene.kaiserlich_scale_thresh_min = bpy.props.FloatProperty(
        name="Min Scale Δ",
        description="Minimum distance change required to detect scaling",
        default=0.5,
        min=0,
        max=2,
        subtype='FACTOR',
    )
    bpy.types.Scene.kaiserlich_scale_thresh_max = bpy.props.FloatProperty(
        name="Max Scale Δ",
        description="Maximum distance change before scaling is considered unstable",
        default=0.5,
        min=0,
        max=2,
        subtype='FACTOR',
    )
    bpy.types.Scene.kaiserlich_rot_scale_thresh_rot = bpy.props.FloatProperty(
        name="Rot+Scale ΔRot",
        description="Sensitivity for combined rotation and scaling (rotation component)",
        default=0.5,
        min=0,
        max=2,
        subtype='FACTOR',
    )
    bpy.types.Scene.kaiserlich_rot_scale_thresh_scale = bpy.props.FloatProperty(
        name="Rot+Scale ΔScale",
        description="Sensitivity for combined rotation and scaling (scale component)",
        default=0.5,
        min=0,
        max=2,
        subtype='FACTOR',
    )
    bpy.types.Scene.kaiserlich_perspective_thresh = bpy.props.FloatProperty(
        name="Perspective Δ",
        description="Sensitivity for perspective deviation (depth/parallax)",
        default=15,
        min=1,
        max=30,
        subtype='FACTOR',
    )
    # --- Progress Display ---
    bpy.types.Scene.kaiserlich_progress_value = bpy.props.FloatProperty(
        name="Progress",
        description="Current progress in percent (0–100)",
        default=1,
        min=0.00001,
        max=100.0,
        soft_min=0.00001,
        soft_max=1,
        subtype='NONE',  # ⬅️ not 'FACTOR', otherwise clamped to 0..1
    )

    bpy.types.Scene.kaiserlich_progress_title = bpy.props.StringProperty(
        name="Status",
        description="Current processing step or title",
        default="",
    )

    bpy.types.Scene.kaiserlich_progress_step = bpy.props.StringProperty(
        name="Step",
        description="Current step title (second line)",
        default="",
    )
    # --- Summary of Quality Analysis (String for UI) ---
    bpy.types.Scene.kaiserlich_quality_percent = bpy.props.StringProperty(
        name="Track Quality",
        description="Pure percentage value of clean tracks (e.g. '51%')",
        default="",
    )
    # --- Marker Tracking Progress (global, for both operators) ---
    bpy.types.Scene.kaiserlich_marker_progress = bpy.props.StringProperty(
        name="Marker Progress",
        description="Percentage of progress (markers per frame across scene)",
        default="",
    )

def unregister():
    for prop in (
        "kaiserlich_rot_thresh_x",
        "kaiserlich_rot_thresh_y",
        "kaiserlich_scale_thresh_min",
        "kaiserlich_scale_thresh_max",
        "kaiserlich_rot_scale_thresh_rot",
        "kaiserlich_rot_scale_thresh_scale",
        "kaiserlich_perspective_thresh",
        "kaiserlich_frames_per_track",
        "max_error_value",
        "kaiserlich_progress_value",
        "kaiserlich_progress_title",
        "kaiserlich_progress_step",
        "kaiserlich_marker_progress",
        "kaiserlich_quality_percent",
    ):
        if hasattr(bpy.types.Scene, prop):
            delattr(bpy.types.Scene, prop)
