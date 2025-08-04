bl_info = {
    "name": "Kaiserlich Tracker",
    "author": "Franz Josef Danner",
    "version": (1, 0),
    "blender": (3, 0, 0),
    "location": "Clip Editor > Sidebar (N) > Kaiserlich",
    "description": "Einfaches Panel im Clip Editor mit Eingaben für Tracking",
    "category": "Tracking",
}

import bpy
from bpy.props import StringProperty, IntProperty, FloatProperty

# -----------------------------
# Panel-Klasse
# -----------------------------

class CLIP_PT_kaiserlich_panel(bpy.types.Panel):
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Kaiserlich"
    bl_label = "Kaiserlich Tracker"

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        layout.label(text="Tracking Einstellungen")
        layout.prop(scene, "marker_frame")
        layout.prop(scene, "frames_track")
        layout.prop(scene, "error_track")
        layout.separator()
        layout.operator("clip.open", text="Clip öffnen")

# -----------------------------
# Registration
# -----------------------------

classes = (
    CLIP_PT_kaiserlich_panel,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.Scene.marker_frame = StringProperty(
        name="Marker per Frame",
        default=20,
        min=10,
        max=50
    )
    bpy.types.Scene.frames_track = IntProperty(
        name="Frames per Track",
        default=20,
        min=5,
        max=100
    )
    bpy.types.Scene.error_track = FloatProperty(
        name="Tracking Error",
        default=0.5,
        min=0.1,
        max=1.0,
    )

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

    del bpy.types.Scene.marker_frame
    del bpy.types.Scene.frames_track
    del bpy.types.Scene.error_track

if __name__ == "__main__":
    register()
