import bpy
from bpy.props import IntProperty

# Szene-Property für gewünschte Marker-Anzahl pro Frame
_def_marker_per_frame = 25

def register():
    bpy.types.Scene.kaiserlich_marker_per_frame = IntProperty(
        name="Marker per Frame",
        default=_def_marker_per_frame,
        min=1,
        soft_max=300,
        description="Ziel-Markerdichte pro Frame (Richtwert)"
    )
    bpy.utils.register_class(CLIP_PT_kaiserlich_tracker)

def unregister():
    if hasattr(bpy.types.Scene, 'kaiserlich_marker_per_frame'):
        del bpy.types.Scene.kaiserlich_marker_per_frame
    bpy.utils.unregister_class(CLIP_PT_kaiserlich_tracker)

class CLIP_PT_kaiserlich_tracker(bpy.types.Panel):
    bl_label = "Kaiserlich Tracker"
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Kaiserlich"

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        layout.prop(scene, "kaiserlich_marker_per_frame")
        layout.operator("clip.kaiserlich_detect_cyclus", text="Detect Cyclus")
