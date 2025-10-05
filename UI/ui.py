import bpy
from bpy.props import IntProperty, StringProperty

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
        box = layout.box()
        box.label(text="Delete Marker")
        box.prop(scn, "kaiserlich_delete_track_name", text="Track (optional)")
        box.operator("kaiserlich.delete_marker", text="Delete Marker Frame")


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
    if not hasattr(bpy.types.Scene, 'kaiserlich_delete_track_name'):
        bpy.types.Scene.kaiserlich_delete_track_name = StringProperty(
            name="Track",
            description="Name des Tracks (leer = alle Tracks)",
            default="",
        )

def unregister():
    if hasattr(bpy.types.Scene, 'kaiserlich_marker_per_frame'):
        try:
            del bpy.types.Scene.kaiserlich_marker_per_frame
        except Exception:
            pass
    if hasattr(bpy.types.Scene, 'kaiserlich_delete_track_name'):
        try:
            del bpy.types.Scene.kaiserlich_delete_track_name
        except Exception:
            pass
    for cls in [KAISERLICH_PT_tracker]:
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass

classes = [KAISERLICH_PT_tracker]
