import bpy
from bpy.types import Panel
from bpy.props import IntProperty


class KAISERLICH_PT_panel(Panel):
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'Kaiserlich'
    bl_label = 'Kaiserlich Tracker'

    @classmethod
    def poll(cls, context):
        space = context.space_data
        return space and getattr(space, 'clip', None) is not None

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        col = layout.column(align=True)
        col.prop(scene, 'kaiserlich_marker_per_frame')
        col.operator('clip.kaiserlich_detect_cycle', text='Detect Cyclus')


def register():
    bpy.types.Scene.kaiserlich_marker_per_frame = IntProperty(
        name="Marker per Frame",
        default=25,
        min=1,
        description="Zielanzahl Marker pro Frame (±10% Toleranz)"
    )
    bpy.utils.register_class(KAISERLICH_PT_panel)


def unregister():
    if hasattr(bpy.types.Scene, 'kaiserlich_marker_per_frame'):
        del bpy.types.Scene.kaiserlich_marker_per_frame
    bpy.utils.unregister_class(KAISERLICH_PT_panel)
