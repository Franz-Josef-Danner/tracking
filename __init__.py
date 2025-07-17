bl_info = {
    "name": "Simple Addon",
    "author": "Your Name",
    "version": (1, 1),
    "blender": (3, 6, 0),
    "location": "View3D > Object",
    "description": "Zeigt eine einfache Meldung an",
    "category": "Object",
}

import bpy

class OBJECT_OT_simple_operator(bpy.types.Operator):
    bl_idname = "object.simple_operator"
    bl_label = "Simple Operator"
    bl_description = "Gibt eine Meldung aus"

    def execute(self, context):
        self.report({'INFO'}, "Hello World from Addon")
        return {'FINISHED'}


class CLIP_OT_panel_button(bpy.types.Operator):
    bl_idname = "clip.panel_button"
    bl_label = "Panel Button"
    bl_description = "Gibt eine Meldung im Clip Editor aus"

    def execute(self, context):
        self.report({'INFO'}, "Button im Clip Editor gedr\u00fcckt")
        return {'FINISHED'}


class CLIP_PT_tracking_panel(bpy.types.Panel):
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'Track'
    bl_label = 'Addon Panel'

    def draw(self, context):
        layout = self.layout
        layout.operator('clip.panel_button')

classes = (
    OBJECT_OT_simple_operator,
    CLIP_OT_panel_button,
    CLIP_PT_tracking_panel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()
