import bpy
from bpy.props import IntProperty

class KAISERLICH_PT_tracker(bpy.types.Panel):
    bl_label = "Kaiserlich Tracker"
    bl_space_type = 'SEQUENCE_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'Kaiserlich'

    def draw(self, context):
        layout = self.layout
        scn = context.scene
        layout.prop(scn, "kaiserlich_marker_per_frame")
        layout.operator("kaiserlich.detect_cycle", text="Detect Cyclus")


def register():
    bpy.types.Scene.kaiserlich_marker_per_frame = IntProperty(
        name="Marker per Frame",
        description="Anzahl Marker pro Frame",
        default=25,
        min=1,
        soft_max=200,
    )


def unregister():
    del bpy.types.Scene.kaiserlich_marker_per_frame

classes = [KAISERLICH_PT_tracker]

def register():
    for cls in classes:
        try:
            bpy.utils.register_class(cls)
        except Exception:
            pass
    if not hasattr(bpy.types.Scene, 'kaiserlich_marker_per_frame'):
        bpy.types.Scene.kaiserlich_marker_per_frame = IntProperty(
            name="Marker per Frame",
            description="Anzahl Marker pro Frame",
            default=25,
            min=1,
            soft_max=200,
        )

def unregister():
    if hasattr(bpy.types.Scene, 'kaiserlich_marker_per_frame'):
        del bpy.types.Scene.kaiserlich_marker_per_frame
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass
