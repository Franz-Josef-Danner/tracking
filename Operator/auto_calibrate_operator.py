# operators/set_thresholds.py
import bpy
from bpy.props import FloatProperty

class KAISERLICHTRACKER_OT_auto_calibrate(bpy.types.Operator):
    """Auto-calibrate: initialisiert alle Ziel-Parameter auf 1 und testet danach jeden Parameter isoliert."""
    bl_idname = "kaiserlich_tracker.auto_calibrate"
    bl_label = "KAISERLICHTRACKER — Auto Calibrate"
    bl_options = {"REGISTER", "UNDO"}

    # Operator-Properties (temporärer Buffer für Dialog)
    rot_thresh_x: FloatProperty(name="ΔX-Threshold",     min=0.0, precision=3)
    rot_thresh_y: FloatProperty(name="ΔY-Threshold",     min=0.0, precision=3)

    scale_thresh_min: FloatProperty(name="Min Scale Δ",  min=0.0, precision=4)
    scale_thresh_max: FloatProperty(name="Max Scale Δ",  min=0.0, precision=4)

    rot_scale_thresh_rot:   FloatProperty(name="Rot+Scale ΔRot",   min=0.0, precision=3)
    rot_scale_thresh_scale: FloatProperty(name="Rot+Scale ΔScale", min=0.0, precision=4)

    perspective_thresh: FloatProperty(name="Perspective Δ", min=0.0, precision=4)

    def invoke(self, context, event):
        s = context.scene
        # aktuelle Scene-Werte in den Dialog spiegeln
        self.rot_thresh_x  = s.kaiserlich_rot_thresh_x
        self.rot_thresh_y  = s.kaiserlich_rot_thresh_y

        self.scale_thresh_min = s.kaiserlich_scale_thresh_min
        self.scale_thresh_max = s.kaiserlich_scale_thresh_max

        self.rot_scale_thresh_rot   = s.kaiserlich_rot_scale_thresh_rot
        self.rot_scale_thresh_scale = s.kaiserlich_rot_scale_thresh_scale

        self.perspective_thresh = s.kaiserlich_perspective_thresh

        return context.window_manager.invoke_props_dialog(self, width=360)

    def draw(self, context):
        layout = self.layout

        layout.label(text="Rotation Thresholds")
        col = layout.column(align=True)
        col.prop(self, "rot_thresh_x")
        col.prop(self, "rot_thresh_y")

        layout.separator()

        layout.label(text="Scale Thresholds")
        col = layout.column(align=True)
        col.prop(self, "scale_thresh_min")
        col.prop(self, "scale_thresh_max")

        layout.separator()

        layout.label(text="LocRotScale Thresholds")
        col = layout.column(align=True)
        col.prop(self, "rot_scale_thresh_rot")
        col.prop(self, "rot_scale_thresh_scale")

        layout.separator()

        layout.label(text="Perspective Thresholds")
        col = layout.column(align=True)
        col.prop(self, "perspective_thresh")

    def execute(self, context):
        s = context.scene

        # Validierung: Min <= Max bei Scale
        if self.scale_thresh_min > self.scale_thresh_max:
            self.report({'ERROR'}, "Min Scale Δ darf nicht größer als Max Scale Δ sein.")
            return {'CANCELLED'}

        # zurückschreiben in Scene
        s.kaiserlich_rot_thresh_x  = self.rot_thresh_x
        s.kaiserlich_rot_thresh_y  = self.rot_thresh_y

        s.kaiserlich_scale_thresh_min = self.scale_thresh_min
        s.kaiserlich_scale_thresh_max = self.scale_thresh_max

        s.kaiserlich_rot_scale_thresh_rot   = self.rot_scale_thresh_rot
        s.kaiserlich_rot_scale_thresh_scale = self.rot_scale_thresh_scale

        s.kaiserlich_perspective_thresh = self.perspective_thresh

        self.report({'INFO'}, "Thresholds aktualisiert.")
        return {'FINISHED'}


def register():
    bpy.utils.register_class(KAISERLICH_OT_set_thresholds)

def unregister():
    bpy.utils.unregister_class(KAISERLICH_OT_set_thresholds)
