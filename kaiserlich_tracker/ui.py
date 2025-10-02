import bpy
from bpy.props import IntProperty


class CLIP_PT_kaiserlich_tracker(bpy.types.Panel):
    bl_label = "Kaiserlich Tracker"
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Kaiserlich"

    @classmethod
    def poll(cls, context):
        space = context.space_data
        return space and getattr(space, 'clip', None) is not None

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        layout.prop(scene, "kaiserlich_marker_per_frame")
        layout.operator("clip.kaiserlich_detect_cyclus", text="Detect Cyclus")


def register():
    if not hasattr(bpy.types.Scene, 'kaiserlich_marker_per_frame'):
        bpy.types.Scene.kaiserlich_marker_per_frame = IntProperty(
            name="Marker per Frame",
            default=25,
            min=1,
            description="Zielanzahl Marker pro Frame (±10% Toleranz)"
        )
    bpy.utils.register_class(CLIP_PT_kaiserlich_tracker)


def unregister():
    bpy.utils.unregister_class(CLIP_PT_kaiserlich_tracker)
    if hasattr(bpy.types.Scene, 'kaiserlich_marker_per_frame'):
        del bpy.types.Scene.kaiserlich_marker_per_frame
