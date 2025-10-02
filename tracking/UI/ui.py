import bpy
from bpy.props import IntProperty
from bpy.types import Panel, Operator

# Global property registration helper

def register_props():
    bpy.types.Scene.tracking_markers_per_frame = IntProperty(
        name="Marker per Frame",
        description="Gewünschte Anzahl erkannter Marker pro Frame",
        default=25,
        min=1,
        soft_max=500,
    )


def unregister_props():
    if hasattr(bpy.types.Scene, "tracking_markers_per_frame"):
        del bpy.types.Scene.tracking_markers_per_frame


class TRACKING_OT_detect_cycle(Operator):
    bl_idname = "tracking.detect_cycle"
    bl_label = "Detect Cyclus"
    bl_description = "Starte iterativen Erkennungs-Zyklus für Feature Marker"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        from tracking.Operator.operator import run_cycle
        run_cycle(context)
        return {'FINISHED'}


class TRACKING_PT_panel(Panel):
    bl_label = "Tracking Automation"
    bl_idname = "TRACKING_PT_panel"
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'Tracking'

    def draw(self, context):
        layout = self.layout
        scn = context.scene
        layout.prop(scn, "tracking_markers_per_frame")
        layout.operator("tracking.detect_cycle", icon='TRACKING')


def register():
    register_props()
    bpy.utils.register_class(TRACKING_OT_detect_cycle)
    bpy.utils.register_class(TRACKING_PT_panel)


def unregister():
    bpy.utils.unregister_class(TRACKING_PT_panel)
    bpy.utils.unregister_class(TRACKING_OT_detect_cycle)
    unregister_props()


if __name__ == "__main__":
    register()
