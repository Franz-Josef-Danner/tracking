bl_info = {
    "name": "Kaiserlich Tracker",
    "author": "Franz Josef Danner",
    "version": (1, 0),
    "blender": (3, 0, 0),
    "location": "Clip Editor > Sidebar (N) > Kaiserlich",
    "description": "Einfaches Panel im Clip Editor",
    "category": "Tracking",
}

import bpy
from bpy.props import StringProperty

# -----------------------------
# Panel-Klasse
# -----------------------------

class CLIP_PT_mein_panel(bpy.types.Panel):
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Kaiserlich"
    bl_label = "Kaiserlich"

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        layout.label(text="Kaiserlich Tracker")
        layout.prop(scene, "marker_frame")
        layout.prop(scene, "frames_track")
        layout.prop(scene, "error_track")
        layout.operator("clip.open", text="Clip öffnen")

# -----------------------------
# Registration
# -----------------------------

classes = (
    CLIP_PT_mein_panel,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    # Property-Namen ohne Sonderzeichen, lowercase, mit _
    bpy.types.Scene.marker_frame = StringProperty(name="Marker per Frame")
    bpy.types.Scene.frames_track = StringProperty(name="Frames per Track")
    bpy.types.Scene.error_track = StringProperty(name="Tracking Error")

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

    del bpy.types.Scene.marker_frame
    del bpy.types.Scene.frames_track
    del bpy.types.Scene.error_track

if __name__ == "__main__":
    register()
