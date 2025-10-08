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

        col = layout.column(align=True)
        col.prop(scene, "kaiserlich_markers_per_frame", text="Marker per Frame")
        col.operator("kaiserlich_tracker.detect_cycle", text="Detect Cyclus")
        col.operator("kaiserlich_tracker.track_cycle", text="Track Cycle")

        # Neue UI-Sektion: Rotation-Schwellenwerte
        layout.separator()
        layout.label(text="Rotation Thresholds")
        col = layout.column(align=True)
        col.prop(scene, "kaiserlich_rot_thresh_x", text="ΔX-Threshold")
        col.prop(scene, "kaiserlich_rot_thresh_y", text="ΔY-Threshold")


# ==========================================================
# Property-Definitionen für Rotation-Thresholds
# ==========================================================

# ==========================================================
# Sicherstellen, dass Properties beim Laden registriert sind
# ==========================================================
def register():
    import bpy

    bpy.types.Scene.kaiserlich_rot_thresh_x = bpy.props.FloatProperty(
        name="ΔX Threshold",
        description="Minimaler ΔX-Unterschied zur Erkennung von Rotation",
        default=0.001,
        min=0.0,
        soft_max=0.01,
        precision=6
    )

    bpy.types.Scene.kaiserlich_rot_thresh_y = bpy.props.FloatProperty(
        name="ΔY Threshold",
        description="Minimaler ΔY-Unterschied zur Erkennung von Rotation",
        default=0.001,
        min=0.0,
        soft_max=0.01,
        precision=6
    )


def unregister():
    import bpy
    if hasattr(bpy.types.Scene, "kaiserlich_rot_thresh_x"):
        del bpy.types.Scene.kaiserlich_rot_thresh_x
    if hasattr(bpy.types.Scene, "kaiserlich_rot_thresh_y"):
        del bpy.types.Scene.kaiserlich_rot_thresh_y


# Automatisch registrieren, wenn Modul einzeln geladen wird
if __name__ == "__main__" or hasattr(bpy, "app"):
    try:
        register()
    except Exception:
        pass


def unregister():
    del bpy.types.Scene.kaiserlich_rot_thresh_x
    del bpy.types.Scene.kaiserlich_rot_thresh_y
