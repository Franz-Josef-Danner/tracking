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

        # Property-Layout: Label links, Feld rechts – ohne dunklen Box-Hintergrund
        col = layout.column(align=True)
        col.use_property_split = True
        col.use_property_decorate = False
        col.prop(scene, "kaiserlich_markers_per_frame", text="Marker per Frame")
        col.prop(scene, "kaiserlich_frames_per_track", text="Frames per Track")
        col.prop(scene, "max_error_value", text="Max error Value")

        # ▶️ Buttons
        col = layout.column(align=True)
        col.operator("kaiserlich_tracker.master_operator", text="Master", icon="SYSTEM")

        # Zwei Buttons nebeneinander
        row = col.row(align=True)
        row.operator("kaiserlich_tracker.shorttest_operator", text="Short Test Thresholds", icon="VIEWZOOM")
        row.operator("kaiserlich_tracker.deep_test_operator", text="Deep Test Thresholds", icon="ZOOM_IN")

        col.operator("kaiserlich_tracker.detect_adapt", text="Run Detect Adapt", icon="STICKY_UVS_DISABLE")
        
        row = col.row(align=True)
        row.operator("kaiserlich_tracker.track_cycle_backwards", text="Track Cycle (Backwards)", icon="TRACKING_BACKWARDS")
        row.operator("kaiserlich_tracker.track_cycle", text="Track Cycle (Forward)", icon="TRACKING_FORWARDS")

        col.operator("kaiserlich_tracker.resolve_operator", text="Run resolve camera", icon="STICKY_UVS_DISABLE")
     
        layout.separator()

        # --- Rotation Thresholds ---
        layout.label(text="Rotation Thresholds")
        col = layout.column(align=True)
        col.use_property_split = True
        col.use_property_decorate = False
        col.prop(scene, "kaiserlich_rot_thresh_x", text="ΔX-Threshold")
        col.prop(scene, "kaiserlich_rot_thresh_y", text="ΔY-Threshold")

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

        col = layout.column(align=True)
        col.scale_y = 1.4
        col.prop(scene, "kaiserlich_progress_title", text=f"{scene.kaiserlich_progress_value * 100:.1f}%")
        col.prop(scene, "kaiserlich_progress_value", text="", slider=True)
        
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
    # --- Fortschrittsanzeige ---
    bpy.types.Scene.kaiserlich_progress_value = bpy.props.FloatProperty(
        name="Progress",
        description="Aktueller Fortschritt in Prozent (0.0–1.0)",
        default=0.0,
        min=0.0,
        max=1.0,
        subtype='FACTOR',
    )

    bpy.types.Scene.kaiserlich_progress_title = bpy.props.StringProperty(
        name="Status",
        description="Aktueller Verarbeitungsschritt oder Titel",
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
    ):
        if hasattr(bpy.types.Scene, prop):
            delattr(bpy.types.Scene, prop)
