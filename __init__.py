bl_info = {
    "name": "Mein Clip Editor Addon",
    "author": "Dein Name",
    "version": (1, 0),
    "blender": (3, 0, 0),
    "location": "Clip Editor > Sidebar (N) > Mein Tab",
    "description": "Einfaches Panel im Clip Editor",
    "category": "Compositing",
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
        layout.prop(scene, "Marker/Frame")
        layout.prop(scene, "Frames/Track")
        layout.prop(scene, "Error/Track")
        layout.operator("clip.open", text="Track")

# -----------------------------
# Registration
# -----------------------------

classes = (
    CLIP_PT_mein_panel,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.Marker_Frame = StringProperty(name="Marker_Frame")
    bpy.types.Scene.Frames_Track = StringProperty(name="Frames_Track")
    bpy.types.Scene.Error_Track3 = StringProperty(name="Error_Track3")

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.Marker_Frame
    del bpy.types.Scene.Frames_Track
    del bpy.types.Scene.Error_Track3

if __name__ == "__main__":
    register()
