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

        # --- Hauptbereich ---
        col = layout.column(align=True)
        col.prop(scene, "kaiserlich_markers_per_frame", text="Marker per Frame")
        col.prop(scene, "kaiserlich_frames_per_track", text="Frames per Track")
        
        # ▶️ Buttons
        col.operator("kaiserlich_tracker.master_operator", text="Master", icon="PLUGIN")
        col.operator("kaiserlich_tracker.shorttest_operator", text="Short Test Thresholds", icon="MOD_WAVE")
        col.operator("kaiserlich_tracker.deep_test", text="Deep Test Thresholds", icon="MOD_WAVE")
        col.operator("kaiserlich_tracker.detect_adapt", text="Run Detect Adapt", icon="FILE_TICK")
        col.operator("kaiserlich_tracker.track_cycle_backwards", text="Track Cycle (Backwards)", icon="TRACKING")
        col.operator("kaiserlich_tracker.track_cycle", text="Track Cycle (Forward)", icon="TRACKING")

        layout.separator()

        # --- Rotation Thresholds ---
        layout.label(text="Rotation Thresholds")
        col = layout.column(align=True)
        col.prop(scene, "kaiserlich_rot_thresh_x", text="ΔX-Threshold")
        col.prop(scene, "kaiserlich_rot_thresh_y", text="ΔY-Threshold")

        layout.separator()

        # --- Scale Thresholds ---
        layout.label(text="Scale Thresholds")
        col = layout.column(align=True)
        col.prop(scene, "kaiserlich_scale_thresh_min", text="Min Scale Δ")
        col.prop(scene, "kaiserlich_scale_thresh_max", text="Max Scale Δ")

        layout.separator()

        # --- LocRotScale Thresholds ---
        layout.label(text="LocRotScale Thresholds")
        col = layout.column(align=True)
        col.prop(scene, "kaiserlich_rot_scale_thresh_rot", text="Rot+Scale ΔRot")
        col.prop(scene, "kaiserlich_rot_scale_thresh_scale", text="Rot+Scale ΔScale")

        layout.separator()

        # --- Perspective Thresholds ---
        layout.label(text="Perspective Thresholds")
        col = layout.column(align=True)
        col.prop(scene, "kaiserlich_perspective_thresh", text="Perspective Δ")


# ==========================================================
# Registrierung der UI-Properties
# ==========================================================

def register():
    bpy.types.Scene.kaiserlich_rot_thresh_x = bpy.props.FloatProperty(
        name="ΔX Threshold",
        description="Minimaler ΔX-Unterschied zur Erkennung von Rotation",
        default=0.001,
        min=0.0,
        soft_max=0.01,
        precision=6,
        subtype='FACTOR',
    )
    bpy.types.Scene.kaiserlich_rot_thresh_y = bpy.props.FloatProperty(
        name="ΔY Threshold",
        description="Minimaler ΔY-Unterschied zur Erkennung von Rotation",
        default=0.001,
        min=0.0,
        soft_max=0.01,
        precision=6,
        subtype='FACTOR',
    )
    bpy.types.Scene.kaiserlich_scale_thresh_min = bpy.props.FloatProperty(
        name="Min Scale Δ",
        description="Minimale Abstandsänderung zur Erkennung von Skalierung",
        default=0.002,
        min=0.0,
        soft_max=0.02,
        precision=6,
        subtype='FACTOR',
    )
    bpy.types.Scene.kaiserlich_scale_thresh_max = bpy.props.FloatProperty(
        name="Max Scale Δ",
        description="Maximale Abstandsänderung, bevor Skalierung als instabil gilt",
        default=0.010,
        min=0.0,
        soft_max=0.05,
        precision=6,
        subtype='FACTOR',
    )
    bpy.types.Scene.kaiserlich_rot_scale_thresh_rot = bpy.props.FloatProperty(
        name="Rot+Scale ΔRot",
        description="Empfindlichkeit für kombinierte Rotation und Skalierung (Rotationsteil)",
        default=0.002,
        min=0.0,
        soft_max=0.02,
        precision=6,
        subtype='FACTOR',
    )
    bpy.types.Scene.kaiserlich_rot_scale_thresh_scale = bpy.props.FloatProperty(
        name="Rot+Scale ΔScale",
        description="Empfindlichkeit für kombinierte Rotation und Skalierung (Skalierungsteil)",
        default=0.005,
        min=0.0,
        soft_max=0.02,
        precision=6,
        subtype='FACTOR',
    )
    bpy.types.Scene.kaiserlich_perspective_thresh = bpy.props.FloatProperty(
        name="Perspective Δ",
        description="Empfindlichkeit für perspektivische Abweichung (Tiefe/Parallaxe)",
        default=0.002,
        min=0.0,
        soft_max=0.02,
        precision=6,
        subtype='FACTOR',
    )
    bpy.types.Scene.kaiserlich_frames_per_track = bpy.props.IntProperty(
        name="Frames per Track",
        description="Mindestanzahl an Frames, die ein Track haben muss, um beim Cleanup nicht gelöscht zu werden",
        default=25,
        min=0,
        soft_min=0,
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
    ):
        if hasattr(bpy.types.Scene, prop):
            delattr(bpy.types.Scene, prop)
