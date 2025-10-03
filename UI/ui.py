import bpy
from bpy.props import IntProperty

class KAISERLICH_PT_tracker(bpy.types.Panel):
    bl_label = "Kaiserlich Tracker"
    bl_space_type = 'CLIP_EDITOR'  # Movie Clip Editor
    bl_region_type = 'UI'
    bl_category = 'Kaiserlich Tracker'

    @classmethod
    def poll(cls, context):
        # Panel nur anzeigen, wenn wir im Movie Clip Editor sind
        return context.space_data and context.space_data.type == 'CLIP_EDITOR'

    def draw(self, context):
        layout = self.layout
        scn = context.scene
        layout.prop(scn, "kaiserlich_marker_per_frame")
        layout.operator("kaiserlich.detect_cycle", text="Detect Cyclus")


def register():
    # Klassen registrieren
    classes = [KAISERLICH_PT_tracker]
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
        try:
            del bpy.types.Scene.kaiserlich_marker_per_frame
        except Exception:
            pass
    for cls in [KAISERLICH_PT_tracker]:
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass

classes = [KAISERLICH_PT_tracker]
