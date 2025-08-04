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
        layout.label(text="Tracker")
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

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()
