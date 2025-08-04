bl_info = {
    "name": "Hallo Welt Panel",
    "author": "ChatGPT",
    "version": (1, 0, 0),
    "blender": (4, 4, 3),
    "location": "View3D > Sidebar",
    "description": "Zeigt ein einfaches Hallo Welt Panel.",
    "category": "3D View",
}

import bpy


class HALLOWORLD_PT_panel(bpy.types.Panel):
    """Ein Panel, das eine Grußnachricht zeigt."""

    bl_label = "Hallo Welt"
    bl_idname = "VIEW3D_PT_hallo_welt"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Tools'

    def draw(self, context):
        layout = self.layout
        layout.label(text="Hallo Welt!")


classes = (HALLOWORLD_PT_panel,)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
