"""UI Panel for the Kaiserlich Tracksycle add-on."""

import bpy
from bpy.props import IntProperty, FloatProperty


class KAISERLICH_PT_tracker(bpy.types.Panel):
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'Kaiserlich Tracker'
    bl_label = 'Kaiserlich Tracker'

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        layout.prop(scene, "kaiserlich_min_marker_count")
        layout.prop(scene, "kaiserlich_min_track_length")
        layout.prop(scene, "kaiserlich_detect_threshold")
        layout.operator("kaiserlich.auto_track_cycle", text="Start")


def register():
    bpy.utils.register_class(KAISERLICH_PT_tracker)
    bpy.types.Scene.kaiserlich_min_marker_count = IntProperty(
        name="Min Marker Count",
        default=10,
    )
    bpy.types.Scene.kaiserlich_min_track_length = IntProperty(
        name="Min Track Length",
        default=5,
    )
    bpy.types.Scene.kaiserlich_detect_threshold = FloatProperty(
        name="Detect Threshold",
        default=0.8,
        min=0.0001,
    )


def unregister():
    bpy.utils.unregister_class(KAISERLICH_PT_tracker)
    del bpy.types.Scene.kaiserlich_min_marker_count
    del bpy.types.Scene.kaiserlich_min_track_length
    del bpy.types.Scene.kaiserlich_detect_threshold


if __name__ == "__main__":
    register()
